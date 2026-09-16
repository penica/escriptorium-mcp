"""Training acceptance and metrics exercised through authenticated HTTP MCP."""

import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter

from tests.test_http import TOKEN, running_endpoint
from tests.training_fixture import training_fixture


async def submit_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        response = await session.call_tool(
            "train_recognition",
            {
                "document_id": 4,
                "job": {"parts": [10], "model": 7, "transcription": 6},
                "track": True,
            },
        )
        assert not response.is_error, response.content
        block = response.content[0]
        assert isinstance(block, TextContent)
        result = TypeAdapter[JsonValue](JsonValue).validate_json(block.text)
        assert isinstance(result, dict)
        assert result["accepted"] is True
        assert result["submission"] == {"status": "ok"}
        tracking = result["tracking"]
        assert isinstance(tracking, dict)
        assert tracking["status"] == "unavailable"


def test_accepted_training_survives_monitoring_failure_over_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with training_fixture("after_failure") as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(submit_over_http)
    assert sum(method == "POST" for method, _route, _body in fixture.requests) == 1
    assert fixture.requests[-1] == ("GET", "/api/documents/4/task_groups/", None)


async def report_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        response = await session.call_tool("get_training_report", {"model_id": 7})
        assert not response.is_error, response.content
        block = response.content[0]
        assert isinstance(block, TextContent)
        result = TypeAdapter[JsonValue](JsonValue).validate_json(block.text)
        assert isinstance(result, dict)
        assert result["accuracy_percent"] == 0.0
        assert result["training"] is False
        assert result["artifact_availability"] == "not_checked"
        assert result["task_model_link"] == "not_requested"
        assert result["task_status"] is None


def test_model_metrics_remain_unverified_artifacts_over_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with training_fixture() as fixture:
        fixture.model.update(
            {"accuracy_percent": 0.0, "file": fixture.url + "media/model.safetensors"}
        )
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(report_over_http)
    assert fixture.requests == [("GET", "/api/models/7/", None)]
