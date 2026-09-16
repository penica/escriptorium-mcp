"""Record filtering and confidence updates across authenticated Streamable HTTP."""

from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.record_fixture import DOCUMENT, RecordFixture, record_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_http(fixture: RecordFixture) -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When modern native records are searched through the authenticated service.
        response = await session.call_tool(
            "list_documents",
            {
                "filters": {
                    "project": 1,
                    "name": "Document",
                    "ordering": ["-parts_count"],
                }
            },
        )
        result = decoded_result(response)
        # Then raw expanded fields remain visible to HTTP clients as to STDIO clients.
        assert isinstance(result, dict)
        assert result["results"] == [fixture.document]
        updated = await session.call_tool(
            "update_document",
            {
                "document_id": 4,
                "changes": {"show_confidence_viz": False},
            },
        )
        assert decoded_result(updated) == {"saved": {"show_confidence_viz": False}}


def test_records_through_authenticated_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an isolated upstream and a real bearer-authenticated MCP endpoint.
    with record_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_http, fixture)
    assert parse_qs(urlsplit(fixture.requests[0][1]).query) == {
        "project": ["1"],
        "name": ["Document"],
        "ordering": ["-parts_count"],
    }
    assert fixture.requests[1:] == [("PATCH", DOCUMENT, {"show_confidence_viz": False})]
