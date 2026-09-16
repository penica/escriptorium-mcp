"""Explicit shared-key editing over authenticated Streamable HTTP."""

import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.metadata_fixture import PAGE_METADATA, metadata_fixture
from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import decoded_result


async def update_key_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When the explicitly global key edit crosses authenticated HTTP MCP.
        response = await session.call_tool(
            "update_shared_metadata_key",
            {
                "target": {"scope": "page", "document_id": 4, "page_id": 10},
                "metadata_id": 93,
                "changes": {"cidoc_id": None},
            },
        )
        # Then the row value survives while the nested key reflects explicit null.
        result = decoded_result(response)
        assert isinstance(result, dict)
        assert result["value"] == "page"
        assert result["key"] == {"name": "place", "cidoc_id": None}


def test_metadata_key_edit_through_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an authenticated MCP endpoint and isolated shared metadata.
    with metadata_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(update_key_over_http)
    assert fixture.requests[-1] == (
        "PATCH",
        PAGE_METADATA + "93/",
        {"key": {"cidoc_id": None}},
    )
    assert fixture.rows[91]["value"] == "same"
    assert fixture.key["cidoc_id"] is None
