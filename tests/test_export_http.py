"""Native export options cross the authenticated HTTP MCP service unchanged."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.export_submission_fixture import EXPORT, export_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def submit_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When a JSON archive request crosses the authenticated service.
        response = await session.call_tool(
            "request_server_export",
            {
                "document_id": 4,
                "export": {
                    "transcription": 2,
                    "file_format": "json",
                    "parts": [11, 12],
                    "region_types": ["Undefined", "Orphan"],
                    "include_images": True,
                    "all_transcriptions": True,
                    "archive_format": "zip",
                },
            },
        )
        # Then the native acceptance has no fabricated completion/job fields.
        assert decoded_result(response) == {"status": "ok"}
        tools = await session.list_tools()
        tool = next(
            tool for tool in tools.tools if tool.name == "request_server_export"
        )
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False
        assert tool.annotations.idempotent_hint is False


def test_export_through_authenticated_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an isolated upstream and authenticated HTTP MCP process.
    with export_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(submit_over_http)
    assert [r for r in fixture.requests if r[0] == "POST"] == [
        (
            "POST",
            EXPORT,
            {
                "transcription": 2,
                "file_format": "json",
                "parts": [11, 12],
                "region_types": ["Undefined", "Orphan"],
                "include_characters": False,
                "include_images": True,
                "all_transcriptions": True,
                "archive_format": "zip",
            },
        ),
    ]
