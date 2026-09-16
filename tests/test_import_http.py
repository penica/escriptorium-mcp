"""Import submissions through authenticated Streamable HTTP MCP."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.import_fixture import IMPORT, import_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def submit_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When a METS URL import crosses the authenticated MCP service.
        response = await session.call_tool(
            "submit_document_import",
            {
                "document_id": 4,
                "source": {
                    "kind": "mets_url",
                    "url": "https://example.org/book.xml",
                    "name": "OCR",
                    "override": False,
                },
                "track": True,
            },
        )
        # Then acceptance survives without overstating discovered group attribution.
        result = decoded_result(response)
        assert isinstance(result, dict)
        assert result["accepted"] is True
        assert result["submission"] == {"status": "ok"}
        tracking = result["tracking"]
        assert isinstance(tracking, dict)
        assert tracking["status"] == "candidate"
        assert tracking["attribution_confirmed"] is False


def test_import_through_authenticated_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an isolated upstream and a real authenticated HTTP MCP process.
    with import_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(submit_over_http)
    assert [r for r in fixture.requests if r[0] == "POST"] == [
        (
            "POST",
            IMPORT,
            {
                "mode": "mets",
                "mets_type": "url",
                "mets_uri": "https://example.org/book.xml",
                "name": "OCR",
                "override": False,
            },
        )
    ]
