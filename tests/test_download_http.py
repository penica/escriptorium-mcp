"""Generated artifact discovery, retrieval and deletion over authenticated HTTP."""

import hashlib
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.download_fixture import (
    BINARY,
    COLLECTION,
    DETAIL,
    FILE,
    FP,
    download_fixture,
)
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_downloads(destination: Path) -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        listed = decoded_result(await session.call_tool("list_downloads", {}))
        assert isinstance(listed, dict)
        assert listed["count"] == 1
        detail = decoded_result(
            await session.call_tool("get_download", {"fingerprint": FP})
        )
        assert isinstance(detail, dict)
        assert detail["fingerprint"] == FP
        response = await session.call_tool(
            "download_generated_export",
            {"fingerprint": FP, "destination": str(destination)},
        )
        downloaded = decoded_result(response)
        assert isinstance(downloaded, dict)
        assert downloaded["sha256"] == hashlib.sha256(BINARY).hexdigest()
        deleted = await session.call_tool("delete_download", {"fingerprint": FP})
        assert not deleted.is_error


def test_download_workflow_over_authenticated_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "HTTP export.zip"
    with download_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_downloads, destination)
    assert destination.read_bytes() == BINARY
    assert fixture.requests == [
        ("GET", COLLECTION),
        ("GET", DETAIL),
        ("GET", DETAIL),
        ("GET", FILE),
        ("DELETE", DETAIL),
    ]
