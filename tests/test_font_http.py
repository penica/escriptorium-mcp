"""Authenticated HTTP exposes raw font metadata without fetching its file URL."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.font_fixture import FONT, FONTS, FontFixture, font_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_http(fixture: FontFixture) -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When an authenticated client discovers and reads native font metadata.
        catalogue = await session.list_tools()
        assert {"list_fonts", "get_font"}.issubset(
            {entry.name for entry in catalogue.tools}
        )
        listed = decoded_result(await session.call_tool("list_fonts", {}))
        detail = decoded_result(await session.call_tool("get_font", {"font_id": 3}))
        # Then no renderer/download behavior is added to either metadata operation.
        assert detail == fixture.font
        assert listed == {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [fixture.font],
        }


def test_font_catalogue_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an isolated API and a real bearer-authenticated HTTP MCP service.
    with font_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_http, fixture)
    assert fixture.requests == [("GET", FONTS, None), ("GET", FONT, None)]
