"""Accepted but inaccessible standalone upload through authenticated HTTP MCP."""

from pathlib import Path

import anyio
import pytest
from httpx2 import AsyncClient, Timeout
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.test_http import TOKEN, running_endpoint
from tests.transcription_fixture import decoded_result
from tests.witness_fixture import WITNESS, WITNESSES, witness_fixture


async def upload_over_http(uploaded: Path) -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=Timeout(30, connect=5),
            follow_redirects=False,
        ) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When the pinned native ownership defect follows an acknowledged upload.
        response = await session.call_tool(
            "upload_textual_witness",
            {
                "upload": {
                    "name": "Reference",
                    "file_path": str(uploaded),
                    "acknowledge_unverified_ownership": True,
                }
            },
        )
        result = decoded_result(response)
        # Then HTTP clients keep acceptance distinct from a failed ownership readback.
        assert isinstance(result, dict)
        assert result["accepted"] is True
        assert result["submission"] == {"pk": 7, "owner": None}
        readback = result["ownership_readback"]
        assert isinstance(readback, dict)
        assert readback["status"] == "unavailable"
        assert readback["reason"] == "readback_failed"


def test_witness_http_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an isolated API and bearer-authenticated MCP service.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Reference", encoding="utf-8")
    with witness_fixture() as fixture:
        fixture.responses["POST " + WITNESSES] = {"pk": 7, "owner": None}
        fixture.failures[WITNESS] = 404
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(upload_over_http, uploaded)
    assert fixture.requests == [("POST", WITNESSES, None), ("GET", WITNESS, None)]
