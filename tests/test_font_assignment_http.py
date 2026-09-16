"""Explicit font clearing crosses the authenticated HTTP MCP transport unchanged."""

import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.font_fixture import DOCUMENT, font_fixture
from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import decoded_result


async def clear_font_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When explicit null is submitted through authenticated Streamable HTTP.
        response = await session.call_tool(
            "update_document",
            {"document_id": 4, "changes": {"transcription_font": None}},
        )
        # Then the successful raw response preserves the clearing operation.
        assert decoded_result(response) == {"saved": {"transcription_font": None}}


def test_font_clear_over_authenticated_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given native font capability on the document endpoint.
    with font_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(clear_font_over_http)
    assert fixture.requests == [
        ("OPTIONS", DOCUMENT, None),
        ("PATCH", DOCUMENT, {"transcription_font": None}),
    ]
