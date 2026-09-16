"""Accepted uploads retain evidence when native ownership cannot be confirmed."""

from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue

from escriptorium_mcp import witness_upload
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.witness_models import WitnessUpload
from tests.transcription_fixture import invoke
from tests.witness_fixture import (
    WITNESS,
    WITNESSES,
    WitnessFixture,
    witness_fixture,
    witness_session,
)


@pytest.mark.parametrize(
    ("created", "readback", "reason"),
    [
        ({"pk": 7, "owner": None}, {"pk": 7, "owner": None}, "missing_owner"),
        ({"pk": 7}, {"pk": 7, "owner": "fixture-owner"}, "missing_owner"),
        ({"pk": 7, "owner": " "}, {"pk": 7, "owner": "fixture-owner"}, "missing_owner"),
        ({"pk": 7, "owner": "fixture-owner"}, {"pk": 7}, "missing_owner"),
        (
            {"pk": 7, "owner": False},
            {"pk": 7, "owner": "fixture-owner"},
            "invalid_create_metadata",
        ),
        (
            {"pk": 7, "owner": "fixture-owner"},
            {"pk": 7, "owner": False},
            "invalid_readback_metadata",
        ),
        (
            {"pk": 7, "owner": "fixture-owner"},
            {"pk": "7", "owner": "fixture-owner"},
            "invalid_readback_metadata",
        ),
        (
            {"pk": 7, "owner": "fixture-owner"},
            {"pk": 8, "owner": "fixture-owner"},
            "identity_mismatch",
        ),
        (
            {"pk": 7, "owner": "fixture-owner"},
            {"pk": 7, "owner": "different"},
            "owner_mismatch",
        ),
    ],
)
def test_anomalous_ownership_never_discards_native_acceptance(
    created: JsonValue,
    readback: JsonValue,
    reason: str,
    tmp_path: Path,
) -> None:
    # Given contradictory native creation or owned-detail metadata.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Text", encoding="utf-8")

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When upload succeeds but functional ownership diagnosis is inconclusive.
            result = await invoke(
                session,
                "upload_textual_witness",
                {
                    "upload": {
                        "name": "Reference",
                        "file_path": str(uploaded),
                        "acknowledge_unverified_ownership": True,
                    }
                },
            )
            # Then both unmodified responses survive without a retry or cleanup.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == created
            diagnostic = result["ownership_readback"]
            assert isinstance(diagnostic, dict)
            assert diagnostic["status"] == "unverified"
            assert diagnostic["reason"] == reason
            assert diagnostic["witness_id"] == 7
            assert diagnostic["record"] == readback

    with witness_fixture() as fixture:
        fixture.responses["POST " + WITNESSES] = created
        fixture.responses[WITNESS] = readback
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", WITNESSES, None), ("GET", WITNESS, None)]


@pytest.mark.parametrize("created", [{}, {"pk": "7"}, {"pk": True}, {"pk": 0}, [7]])
def test_missing_identity_is_accepted_without_invented_read_route(
    tmp_path: Path, created: JsonValue
) -> None:
    # Given a native success body lacking a strict positive witness primary key.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Text", encoding="utf-8")

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the upload returns that successful but incomplete response.
            result = await invoke(
                session,
                "upload_textual_witness",
                {
                    "upload": {
                        "name": "Reference",
                        "file_path": str(uploaded),
                        "acknowledge_unverified_ownership": True,
                    }
                },
            )
            # Then the accepted response remains available without a fabricated GET.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == created
            diagnostic = result["ownership_readback"]
            assert isinstance(diagnostic, dict)
            assert diagnostic["status"] == "unavailable"
            assert diagnostic["reason"] == "missing_identity"
            assert diagnostic["witness_id"] is None
            assert diagnostic["record"] is None

    with witness_fixture() as fixture:
        fixture.responses["POST " + WITNESSES] = created
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", WITNESSES, None)]


@pytest.mark.parametrize("status", [404, 500])
def test_ownership_read_failure_preserves_acceptance_with_one_wire_get(
    tmp_path: Path, status: int
) -> None:
    # Given the ownerless-create defect or a readback server failure after acceptance.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Text", encoding="utf-8")

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the diagnostic owned-detail GET fails.
            result = await invoke(
                session,
                "upload_textual_witness",
                {
                    "upload": {
                        "name": "Reference",
                        "file_path": str(uploaded),
                        "acknowledge_unverified_ownership": True,
                    }
                },
            )
            # Then native acceptance survives without asserting definitive ownership.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"pk": 7, "owner": None}
            diagnostic = result["ownership_readback"]
            assert isinstance(diagnostic, dict)
            assert diagnostic["status"] == "unavailable"
            assert diagnostic["reason"] == "readback_failed"
            assert diagnostic["record"] is None
            assert isinstance(diagnostic["error"], str)
            assert "fixture-key" not in diagnostic["error"]

    with witness_fixture() as fixture:
        fixture.responses["POST " + WITNESSES] = {"pk": 7, "owner": None}
        fixture.failures[WITNESS] = status
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", WITNESSES, None), ("GET", WITNESS, None)]


def test_local_readback_failure_does_not_erase_accepted_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a successful POST followed by local worker setup failure on its readback.

    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Reference", encoding="utf-8")
    calls: list[ApiRequest] = []
    native: JsonValue = {"pk": 7, "owner": "fixture-owner"}

    async def fail_readback(
        request: ApiRequest, *, timeout_seconds: float = 120
    ) -> JsonValue:
        assert timeout_seconds > 0
        calls.append(request)
        if len(calls) == 1:
            return native
        msg = "fixture-sensitive-local-path"
        raise FileNotFoundError(msg)

    monkeypatch.setattr(witness_upload, "call", fail_readback)
    # When the functional ownership diagnostic cannot start its worker process.
    result = anyio.run(
        witness_upload.submit_witness,
        WitnessUpload.model_validate(
            {
                "name": "Reference",
                "file_path": uploaded,
                "acknowledge_unverified_ownership": True,
            }
        ),
    )
    # Then native acceptance survives and local failure details are sanitized.
    assert isinstance(result, dict)
    assert result["accepted"] is True
    assert result["submission"] == native
    readback = result["ownership_readback"]
    assert isinstance(readback, dict)
    assert readback["status"] == "unavailable"
    assert readback["reason"] == "readback_failed"
    assert "fixture-sensitive-local-path" not in str(readback["error"])
    assert [call.method for call in calls] == ["POST", "GET"]
    assert all(call.single_attempt is True for call in calls)
