"""Generated download metadata discovery through real STDIO MCP."""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from tests.download_fixture import (
    COLLECTION,
    DETAIL,
    FP,
    OTHER_FP,
    DownloadFixture,
    download_fixture,
    download_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_list_downloads_preserves_metadata() -> None:
    async def run(fixture: DownloadFixture) -> None:
        async with download_session(fixture) as session:
            result = await invoke(session, "list_downloads", {})
            assert isinstance(result, (dict, list))
            rows = result["results"] if isinstance(result, dict) else result
            assert rows == [fixture.detail]

    with download_fixture() as fixture:
        anyio.run(run, fixture)


@pytest.mark.parametrize("envelope", [False, True])
def test_bare_and_paginated_local_report_filter(*, envelope: bool) -> None:
    # Given rows with zero, null and a matching report only on the final page.
    with download_fixture() as fixture:
        first = dict(fixture.detail, task_report_id=None)
        second = dict(
            fixture.detail, fingerprint=OTHER_FP, task_report_id=7, file_size=0
        )
        fixture.responses[COLLECTION] = [first, second]
        if envelope:
            fixture.responses[COLLECTION] = {
                "count": 2,
                "next": "?page=2",
                "results": [first],
            }
            fixture.responses[COLLECTION + "?page=2"] = {
                "count": 2,
                "next": None,
                "results": [second],
            }

        async def run() -> None:
            async with download_session(fixture) as session:
                # When local report filtering is requested.
                result = await invoke(session, "list_downloads", {"task_report_id": 7})
                assert isinstance(result, (dict, list))
                rows = result["results"] if isinstance(result, dict) else result
                # Then the matching row retains all native metadata.
                assert rows == [second]

        anyio.run(run)
    assert fixture.requests == [("GET", COLLECTION)] + (
        [("GET", COLLECTION + "?page=2")] if envelope else []
    )


def test_detail_preserves_expired_metadata() -> None:
    with download_fixture() as fixture:
        fixture.detail.update(is_expired=True, expires_at="2026-09-15T00:00:00Z")

        async def run() -> None:
            async with download_session(fixture) as session:
                result = await invoke(session, "get_download", {"fingerprint": FP})
                assert result == fixture.detail

        anyio.run(run)
    assert fixture.requests == [("GET", DETAIL)]


@pytest.mark.parametrize("tool", ["get_download", "download_generated_export"])
def test_metadata_identity_mismatch_rejected(tmp_path: Path, tool: str) -> None:
    with download_fixture() as fixture:
        fixture.detail["fingerprint"] = OTHER_FP

        async def run() -> None:
            async with download_session(fixture) as session:
                args: dict[str, JsonValue] = {"fingerprint": FP}
                if tool == "download_generated_export":
                    args["destination"] = str(tmp_path / "export.zip")
                response = await session.call_tool(tool, args)
                assert response.is_error

        anyio.run(run)
    assert fixture.requests == [("GET", DETAIL)]
    assert not (tmp_path / "export.zip").exists()


@pytest.mark.parametrize("status", [403, 404])
@pytest.mark.parametrize("tool", ["list_downloads", "get_download"])
def test_metadata_denial_propagates_once(tool: str, status: int) -> None:
    with download_fixture() as fixture:
        route = COLLECTION if tool == "list_downloads" else DETAIL
        fixture.failures[route] = status

        async def run() -> None:
            async with download_session(fixture) as session:
                args = {} if tool == "list_downloads" else {"fingerprint": FP}
                response = await session.call_tool(tool, args)
                assert response.is_error
                assert "fixture-key" not in str(response.content)

        anyio.run(run)
    assert fixture.requests == [("GET", route)]
