"""Collection segmentation training through authenticated HTTP MCP."""

import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.collection_training_fixture import COLLECTION, collection_training_fixture
from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import decoded_result


async def train_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When a two-page collection is submitted through authenticated MCP.
        response = await session.call_tool(
            "train_collection_segmenter",
            {
                "collection_id": 5,
                "job": {"model": 7, "model_name": "segment clone", "override": False},
            },
        )
        # Then the response preserves the confirmed model and server extension field.
        assert decoded_result(response) == {
            "status": "ok",
            "model_id": 9,
            "custom": "retained",
        }


def test_collection_training_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given isolated source documents and an available segmentation model.
    with collection_training_fixture() as fixture:
        fixture.model["job"] = 1
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(train_over_http)
    assert fixture.requests[-1] == (
        "POST",
        COLLECTION + "train_segmenter/",
        {"model": 7, "model_name": "segment clone", "override": False},
    )
