"""Segmentation writes through authenticated Streamable HTTP MCP."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.segmentation_fixture import LINES, segmentation_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def update_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When a nullable geometry update crosses authenticated MCP HTTP.
        response = await session.call_tool(
            "bulk_update_lines",
            {
                "document_id": 4,
                "page_id": 10,
                "lines": [{"pk": 11, "baseline": None, "external_id": "č"}],
            },
        )
        # Then the upstream mask and nested text survive the partial update.
        result = decoded_result(response)
        assert isinstance(result, dict)
        rows = result["lines"]
        assert isinstance(rows, list)
        row = rows[0]
        assert isinstance(row, dict)
        assert row["baseline"] is None
        assert row["external_id"] == "č"
        assert row["mask"] == [[0, 0], [4, 0], [4, 2]]
        assert row["transcriptions"] == [
            {
                "pk": 91,
                "line": 11,
                "transcription": 2,
                "content": "text-11",
                "graphs": [],
                "versions": ["old"],
            }
        ]


def test_bulk_geometry_update_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given real HTTP MCP and a local scoped upstream API fixture.
    with segmentation_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(update_over_http)
    assert fixture.requests[-1] == (
        "PUT",
        LINES + "bulk_update/",
        {"lines": [{"pk": 11, "baseline": None, "external_id": "č"}]},
    )
