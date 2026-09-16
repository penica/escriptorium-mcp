"""Alignment submission through authenticated Streamable HTTP MCP."""

from time import sleep

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import JsonValue

from tests.alignment_fixture import (
    ALIGN,
    DOC,
    AlignmentFixture,
    alignment_fixture,
    alignment_job,
)
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def align_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When an acknowledged zero-offset alignment crosses authenticated HTTP.
        response = await session.call_tool(
            "align_document",
            {
                "document_id": 4,
                "job": alignment_job(
                    {"search": {"kind": "offset", "max_offset": 0}, "threshold": 0}
                ),
                "track": True,
            },
        )
        # Then acceptance survives with unconfirmed optional tracking.
        result = decoded_result(response)
        assert isinstance(result, dict)
        assert result["accepted"] is True
        assert result["submission"] == {"status": "ok"}
        tracking = result["tracking"]
        assert isinstance(tracking, dict)
        assert tracking["status"] == "candidate"
        assert tracking["attribution_confirmed"] is False


@pytest.mark.parametrize(
    "preflight_delay", [0.0, 5.2], ids=["normal", "slow_preflight"]
)
def test_alignment_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch, preflight_delay: float
) -> None:
    # Given an authenticated MCP server and isolated upstream scopes.
    original = AlignmentFixture.respond

    def delayed_document(
        fixture: AlignmentFixture, method: str, path: str, body: JsonValue
    ) -> tuple[int, JsonValue]:
        # Given upstream work exceeding the generic client's five-second deadline.
        if method == "GET" and path == DOC:
            sleep(preflight_delay)
        return original(fixture, method, path, body)

    monkeypatch.setattr(AlignmentFixture, "respond", delayed_document)
    with alignment_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(align_over_http)
    writes = [record for record in fixture.requests if record[0] == "POST"]
    assert len(writes) == 1
    assert writes[0][1] == ALIGN
    body = writes[0][2]
    assert isinstance(body, dict)
    assert body["beam_size"] == body["max_offset"] == body["threshold"] == 0
