"""Native witness uploads and owned edits preserve exact file bytes."""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from tests.transcription_fixture import invoke
from tests.witness_fixture import (
    WITNESS,
    WITNESSES,
    WitnessFixture,
    witness_fixture,
    witness_session,
)

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_upload_reports_verified_owned_creation(tmp_path: Path) -> None:
    # Given a fixed backend that assigns ownership and exposes the created record.
    uploaded = tmp_path / "Reference.TXT"
    _ = uploaded.write_bytes(b"\xef\xbb\xbfText \xc4\x8d\r\n")

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When standalone upload is explicitly acknowledged.
            result = await invoke(
                session,
                "upload_textual_witness",
                {
                    "upload": {
                        "name": "  Reference  ",
                        "file_path": str(uploaded),
                        "acknowledge_unverified_ownership": True,
                    }
                },
            )
            # Then acceptance and owned visibility are reported separately.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == fixture.witness
            readback = result["ownership_readback"]
            assert isinstance(readback, dict)
            assert readback["status"] == "verified"
            assert readback["reason"] is None
            assert readback["witness_id"] == 7
            assert readback["record"] == fixture.witness

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[0] == ("POST", WITNESSES, None)
    assert len(fixture.uploads) == 1
    assert b'name="file"; filename="Reference.TXT"' in fixture.uploads[0]
    assert b'name="name"\r\n\r\nReference\r\n' in fixture.uploads[0]
    assert uploaded.read_bytes() in fixture.uploads[0]
    assert b"acknowledge_unverified_ownership" not in fixture.uploads[0]


def test_owned_rename_replacement_and_delete_have_no_post_write_readback(
    tmp_path: Path,
) -> None:
    # Given a valid owned witness and a replacement UTF-8 file.
    uploaded = tmp_path / "replacement.txt"
    _ = uploaded.write_bytes(b"Replacement\r\n\xef\xbb\xbf\xc4\x8d")

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When a caller renames, replaces and deletes the witness explicitly.
            _ = await invoke(
                session,
                "update_textual_witness",
                {
                    "witness_id": 7,
                    "changes": {"name": "  Renamed  "},
                },
            )
            _ = await invoke(
                session,
                "update_textual_witness",
                {
                    "witness_id": 7,
                    "changes": {"file_path": str(uploaded)},
                },
            )
            deleted = await invoke(session, "delete_textual_witness", {"witness_id": 7})
            # Then native bodyless success requires no speculative follow-up query.
            assert deleted == {"status": "success", "http_status": 204}

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", WITNESS, None),
        ("PATCH", WITNESS, {"name": "Renamed"}),
        ("GET", WITNESS, None),
        ("PATCH", WITNESS, None),
        ("GET", WITNESS, None),
        ("DELETE", WITNESS, {}),
    ]
    assert len(fixture.uploads) == 1
    assert b'name="file"; filename="replacement.txt"' in fixture.uploads[0]
    assert uploaded.read_bytes() in fixture.uploads[0]
    assert b'name="name"' not in fixture.uploads[0]


@pytest.mark.parametrize("action", ["upload", "update", "delete"])
def test_native_write_failure_is_sent_once_without_cleanup(
    tmp_path: Path, action: str
) -> None:
    # Given a native error after a potentially partial witness mutation.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Reference", encoding="utf-8")
    calls: dict[str, tuple[str, dict[str, JsonValue], str]] = {
        "upload": (
            "upload_textual_witness",
            {
                "upload": {
                    "name": "Reference",
                    "file_path": str(uploaded),
                    "acknowledge_unverified_ownership": True,
                }
            },
            "POST " + WITNESSES,
        ),
        "update": (
            "update_textual_witness",
            {"witness_id": 7, "changes": {"name": "New"}},
            "PATCH " + WITNESS,
        ),
        "delete": ("delete_textual_witness", {"witness_id": 7}, "DELETE " + WITNESS),
    }
    tool, args, failure = calls[action]

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the sole native mutation returns a server error.
            result = await session.call_tool(tool, args)
            # Then it remains an error and no API-key data escapes.
            assert result.is_error
            assert "fixture-key" not in result.model_dump_json()

    with witness_fixture() as fixture:
        fixture.failures[failure] = 500
        anyio.run(run, fixture)
    mutations = [r for r in fixture.requests if r[0] != "GET"]
    assert len(mutations) == 1
    assert len(fixture.requests) == (1 if action == "upload" else 2)
