from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter

from tests.model_fixture import model_fixture
from tests.test_http import authenticated_client, running_endpoint


async def download_over_http(destination: Path) -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        response = await session.call_tool(
            "download_model",
            {"model_id": 7, "destination": str(destination), "revision": "revision-1"},
        )
        assert not response.is_error
        block = response.content[0]
        assert isinstance(block, TextContent)
        result = TypeAdapter[JsonValue](JsonValue).validate_json(block.text)
        assert isinstance(result, dict)
        assert result["status"] == "complete"
        assert result["bytes"] == (await anyio.Path(destination).stat()).st_size


def test_checkpoint_download_when_using_authenticated_http(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with model_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        destination = tmp_path / "checkpoint.ckpt"
        anyio.run(download_over_http, destination)
        assert destination.read_bytes() == fixture.binary
