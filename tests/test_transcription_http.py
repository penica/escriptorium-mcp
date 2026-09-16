"""Bulk text writing through authenticated Streamable HTTP MCP."""

import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import TEXTS, decoded_result, transcription_fixture


async def update_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When a nullable metadata patch crosses authenticated HTTP MCP.
        response = await session.call_tool(
            "bulk_update_line_transcriptions",
            {
                "document_id": 4,
                "page_id": 10,
                "lines": [{"pk": 91, "content": "č", "graphs": None}],
            },
        )
        # Then the actual upstream row and its unrelated history survive.
        result = decoded_result(response)
        assert isinstance(result, list)
        row = result[0]
        assert isinstance(row, dict)
        assert row["content"] == "č"
        assert row["graphs"] is None
        assert row["avg_confidence"] == 0.0
        assert row["versions"] == [{"content": "history"}]


def test_nullable_text_update_through_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real MCP HTTP service and isolated upstream fixture.
    with transcription_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(update_over_http)
    assert fixture.requests[-1] == (
        "PUT",
        TEXTS + "bulk_update/",
        {"lines": [{"pk": 91, "content": "č", "graphs": None}]},
    )
