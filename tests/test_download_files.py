"""Native files stream from a fingerprint-derived route into exclusive storage."""

import hashlib
from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue

from tests.download_fixture import (
    BINARY,
    DETAIL,
    FILE,
    FP,
    DownloadFixture,
    download_fixture,
    download_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    "file_url", ["https://untrusted.invalid/private", "/api/tasks/", None]
)
def test_file_uses_fixed_route_and_verifies_bytes(
    tmp_path: Path, file_url: JsonValue
) -> None:
    # Given an untrusted metadata URL and a destination containing spaces.
    destination = tmp_path / "export with spaces.zip"
    with download_fixture() as fixture:
        fixture.detail["file_url"] = file_url

        async def run() -> None:
            async with download_session(fixture) as session:
                result = await invoke(
                    session,
                    "download_generated_export",
                    {"fingerprint": FP, "destination": str(destination)},
                )
                assert isinstance(result, dict)
                assert result["status"] == "complete"
                assert result["bytes"] == len(BINARY)
                assert result["sha256"] == hashlib.sha256(BINARY).hexdigest()
                assert Path(str(result["path"])) == destination

        anyio.run(run)
    assert destination.read_bytes() == BINARY
    assert not destination.with_name(destination.name + ".part").exists()
    assert fixture.requests == [("GET", DETAIL), ("GET", FILE)]


async def failed_file(
    fixture: DownloadFixture, destination: Path, expected_status: int | None = None
) -> None:
    async with download_session(fixture) as session:
        response = await session.call_tool(
            "download_generated_export",
            {"fingerprint": FP, "destination": str(destination)},
        )
        assert response.is_error
        if expected_status is not None:
            assert str(expected_status) in str(response.content)
        assert "fixture-key" not in str(response.content)


@pytest.mark.parametrize("delta", [-1, 1])
def test_metadata_size_mismatch_preserves_partial(tmp_path: Path, delta: int) -> None:
    destination = tmp_path / "export.zip"
    with download_fixture() as fixture:
        fixture.detail["file_size"] = len(BINARY) + delta
        anyio.run(failed_file, fixture, destination)
    assert not destination.exists()
    assert destination.with_name(destination.name + ".part").read_bytes() == BINARY
    assert fixture.requests == [("GET", DETAIL), ("GET", FILE)]


def test_truncated_stream_preserves_partial(tmp_path: Path) -> None:
    destination = tmp_path / "export.zip"
    with download_fixture() as fixture:
        fixture.binary.extend([BINARY, BINARY, BINARY])
        fixture.detail["file_size"] = len(BINARY) * 4
        fixture.headers["Content-Length"] = str(len(BINARY) * 4 + 100)
        anyio.run(failed_file, fixture, destination)
    assert not destination.exists()
    partial = destination.with_name(destination.name + ".part")
    assert partial.exists()
    assert (BINARY * 4).startswith(partial.read_bytes())
    assert partial.stat().st_size > 0
    assert fixture.requests == [("GET", DETAIL), ("GET", FILE)]


@pytest.mark.parametrize("size", [-1, "12", True, None])
def test_invalid_metadata_size_prevents_file_get(
    tmp_path: Path, size: JsonValue
) -> None:
    destination = tmp_path / "export.zip"
    with download_fixture() as fixture:
        fixture.detail["file_size"] = size
        anyio.run(failed_file, fixture, destination)
    assert not destination.exists()
    assert fixture.requests == [("GET", DETAIL)]


@pytest.mark.parametrize("status", [403, 404, 500])
def test_failed_file_get_is_not_retried(tmp_path: Path, status: int) -> None:
    destination = tmp_path / "export.zip"
    with download_fixture() as fixture:
        fixture.failures[FILE] = status
        anyio.run(failed_file, fixture, destination, status)
    assert not destination.exists()
    assert fixture.requests == [("GET", DETAIL), ("GET", FILE)]


def test_expired_metadata_does_not_claim_local_success(tmp_path: Path) -> None:
    destination = tmp_path / "export.zip"
    with download_fixture() as fixture:
        fixture.detail["is_expired"] = True
        fixture.failures[FILE] = 404
        anyio.run(failed_file, fixture, destination)
    assert not destination.exists()
    assert fixture.requests[0] == ("GET", DETAIL)
    assert all(path in {DETAIL, FILE} for _, path in fixture.requests)


def test_redirected_file_does_not_forward_token(tmp_path: Path) -> None:
    destination = tmp_path / "export.zip"
    with download_fixture() as fixture, download_fixture() as foreign:
        fixture.redirects[FILE] = foreign.url + "private"
        anyio.run(failed_file, fixture, destination)
    assert not destination.exists()
    assert fixture.requests == [("GET", DETAIL), ("GET", FILE)]
    assert not foreign.requests


def test_zero_byte_file_is_valid(tmp_path: Path) -> None:
    destination = tmp_path / "empty.zip"
    with download_fixture() as fixture:
        fixture.binary.clear()
        fixture.detail["file_size"] = 0

        async def run() -> None:
            async with download_session(fixture) as session:
                result = await invoke(
                    session,
                    "download_generated_export",
                    {"fingerprint": FP, "destination": str(destination)},
                )
                assert isinstance(result, dict)
                assert result["bytes"] == 0
                assert result["sha256"] == hashlib.sha256(b"").hexdigest()

        anyio.run(run)
    assert destination.read_bytes() == b""
