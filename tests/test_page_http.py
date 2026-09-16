"""Page image actions through authenticated Streamable HTTP MCP."""

import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.page_fixture import PAGE, page_fixture
from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import decoded_result


@pytest.mark.parametrize("tool", ["rotate_page", "crop_page"])
def test_image_action_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    # Given an authenticated MCP HTTP service and isolated upstream API.
    with page_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")

        async def scenario() -> None:
            async with (
                running_endpoint() as endpoint,
                AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
                Client(streamable_http_client(endpoint, http_client=http)) as session,
            ):
                payload = (
                    {"angle": 90}
                    if tool == "rotate_page"
                    else {"box": {"x1": 0, "y1": 0, "x2": 50, "y2": 40}}
                )
                # When the image action crosses the HTTP transport boundary.
                result = await session.call_tool(
                    tool, {"document_id": 4, "page_id": 10, **payload}
                )
                # Then synchronous native completion is returned unchanged.
                assert decoded_result(result) == {"status": "done"}

        anyio.run(scenario)
    assert fixture.requests[0] == ("GET", PAGE, None)
    assert len([item for item in fixture.requests if item[0] == "POST"]) == 1
