import anyio
import pytest
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter

from tests.task_fixture import report, task_fixture
from tests.test_http import TOKEN, running_endpoint


async def read_job_status_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        result = await session.call_tool(
            "get_document_job_status", {"document_id": 7, "group_id": 4}
        )
        assert not result.is_error
        content = result.content[0]
        assert isinstance(content, TextContent)
        status = TypeAdapter[JsonValue](JsonValue).validate_json(content.text)
        assert isinstance(status, dict)
        assert status["total"] == 2
        assert status["terminal_percent"] == 50
        assert status["has_active"] is True
        assert status["all_finished"] is False


def test_task_summary_when_using_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with task_fixture([report(1, 1), report(2, 3)]) as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(read_job_status_over_http)
