"""Untrusted fingerprint and report selectors fail before upstream requests."""

import anyio
import pytest
from pydantic import JsonValue

from tests.download_fixture import download_fixture, download_session


@pytest.mark.parametrize(
    "fingerprint",
    [
        "",
        "a" * 31,
        "a" * 33,
        "A" * 32,
        "g" * 32,
        "../private",
        "a" * 32 + "/file",
        7,
        None,
    ],
)
def test_invalid_fingerprints_make_no_requests(fingerprint: JsonValue) -> None:
    # Given malformed routing input, exercise all public fingerprint boundaries.
    with download_fixture() as fixture:

        async def run() -> None:
            async with download_session(fixture) as session:
                for tool in (
                    "get_download",
                    "delete_download",
                    "download_generated_export",
                ):
                    args: dict[str, JsonValue] = {"fingerprint": fingerprint}
                    if tool == "download_generated_export":
                        args["destination"] = "export.zip"
                    response = await session.call_tool(tool, args)
                    assert response.is_error

        anyio.run(run)
    assert not fixture.requests


@pytest.mark.parametrize("report", [0, -1, True, "7", 1.5])
def test_invalid_report_filter_makes_no_requests(report: JsonValue) -> None:
    with download_fixture() as fixture:

        async def run() -> None:
            async with download_session(fixture) as session:
                response = await session.call_tool(
                    "list_downloads", {"task_report_id": report}
                )
                assert response.is_error

        anyio.run(run)
    assert not fixture.requests
