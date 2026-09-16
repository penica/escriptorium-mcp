import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

import anyio
import pytest
import uvicorn
from httpx2 import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import TextContent
from pydantic import TypeAdapter

from escriptorium_mcp.server import create_server
from escriptorium_mcp.transport import http_app
from tests.test_stdio import ProjectPage, api_fixture

TOKEN: Final = "fixture-service-token-32-characters-minimum"  # noqa: S105


@asynccontextmanager
async def running_endpoint() -> AsyncGenerator[str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = TypeAdapter(tuple[str, int]).validate_python(listener.getsockname())[1]
        app = http_app(create_server(), TOKEN, [f"127.0.0.1:{port}"], [])
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
        async with anyio.create_task_group() as tasks:
            _ = tasks.start_soon(server.serve, [listener])
            try:
                with anyio.fail_after(10):
                    while not server.started:  # noqa: ASYNC110 - Uvicorn exposes a flag.
                        await anyio.sleep(0.01)
                yield f"http://127.0.0.1:{port}/mcp"
            finally:
                server.should_exit = True


async def exercise_http() -> None:
    async with (
        running_endpoint() as endpoint,
        AsyncClient() as anonymous,
        AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as authenticated,
    ):
        denied = await anonymous.post(endpoint, json={})
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"] == "Bearer"
        for headers in (
            {"Origin": "https://untrusted.example"},
            {"Host": "untrusted.example"},
        ):
            blocked = await authenticated.post(endpoint, headers=headers, json={})
            assert blocked.status_code in {403, 421}
        async with Client(
            streamable_http_client(endpoint, http_client=authenticated)
        ) as session:
            discovered = await session.list_tools()
            assert len(discovered.tools) == 173
            result = await session.call_tool("list_projects")
            assert not result.is_error
            content = result.content[0]
            assert isinstance(content, TextContent)
            projects = ProjectPage.model_validate_json(content.text)
            assert [project.id for project in projects.results] == [1, 2]


def test_authenticated_http_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    with api_fixture() as url:
        monkeypatch.setenv("ESCRIPTORIUM_URL", url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_http)


@pytest.mark.parametrize("token", ["", "short", "x" * 31, "x" * 32 + " "])
def test_http_rejects_missing_or_unsafe_token(token: str) -> None:
    with pytest.raises(ValueError, match="ESCRIPTORIUM_HTTP_TOKEN"):
        _ = http_app(create_server(), token, ["127.0.0.1:8000"], [])


@pytest.mark.parametrize("hosts", [[], ["*"], ["*.example.com:8000"]])
def test_http_rejects_wildcard_hosts(hosts: list[str]) -> None:
    with pytest.raises(ValueError, match="concrete allowed HTTP hostnames"):
        _ = http_app(create_server(), TOKEN, hosts, [])
