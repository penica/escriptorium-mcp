"""Collection creation and native membership reads through authenticated HTTP."""

import anyio
import pytest
from httpx2 import AsyncClient, Timeout
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.collection_fixture import COLLECTIONS, CollectionFixture, collection_fixture
from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_http(fixture: CollectionFixture) -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=Timeout(30, connect=5),
            follow_redirects=False,
        ) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When the client creates a collection with an explicit empty member selection.
        created = await session.call_tool(
            "create_collection",
            {
                "data": {"name": "HTTP", "items": [], "default_transcriptions": {}},
            },
        )
        # Then native metadata and the intentional empty selection cross HTTP intact.
        assert decoded_result(created) == fixture.collection
        items = await session.call_tool("list_collection_items", {"collection_id": 7})
        assert decoded_result(items) == {"count": 0, "next": None, "results": []}
        tools = await session.list_tools()
        deletion = next(
            tool for tool in tools.tools if tool.name == "delete_collection"
        )
        assert deletion.annotations is not None
        assert deletion.annotations.destructive_hint is True


def test_collection_http_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a real bearer-authenticated MCP service and isolated collection API.
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_http, fixture)
    assert [r for r in fixture.requests if r[0] == "POST"] == [
        (
            "POST",
            COLLECTIONS,
            {"name": "HTTP", "items_to_save": [], "default_transcriptions": {}},
        ),
    ]
