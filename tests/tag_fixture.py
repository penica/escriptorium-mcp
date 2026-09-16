"""Isolated native tag definitions with scoped routes and recorded writes."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final, final
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

PROJECT: Final = "/api/projects/7/"
PERSONAL: Final = "/api/tags/project/"
PROJECT_TAGS: Final = PROJECT + "tags/"


@dataclass(frozen=True, slots=True)
class TagFixture:
    """Mutable containers configure upstream state and capture requests."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    project: dict[str, JsonValue] = field(default_factory=lambda: {"id": 7})
    tag: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 2,
            "name": "Review",
            "color": "#123456",
            "future": 0,
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        failure = self.failures.get(f"{method} {path}", self.failures.get(path))
        if failure is not None:
            return failure, {"detail": "Fixture denied or conflict"}
        if method == "GET":
            return self.read(path)
        if method == "DELETE":
            return 204, None
        if method in {"POST", "PATCH"}:
            assert isinstance(body, dict)
            self.tag.update(body)
            return (201 if method == "POST" else 200), self.tag
        return 405, {"detail": "Unexpected operation"}

    def read(self, path: str) -> tuple[int, JsonValue]:
        if path in self.responses:
            return 200, self.responses[path]
        if path == PROJECT:
            return 200, self.project
        route = urlsplit(path).path
        if route in {PERSONAL, PROJECT_TAGS}:
            return 200, {
                "count": 1,
                "next": None,
                "results": [self.tag],
                "extra": "keep",
            }
        if route in {PERSONAL + "2/", PROJECT_TAGS + "2/"}:
            return 200, self.tag
        return 404, {"detail": "Unknown fixture route"}


@contextmanager
def tag_fixture() -> Generator[TagFixture]:
    fixture = TagFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
            self.send_response(status)
            if status == 204:
                self.end_headers()
                return
            payload = TypeAdapter[JsonValue](JsonValue).dump_json(result)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

        def do_GET(self) -> None:
            self.respond()

        def do_POST(self) -> None:
            self.respond()

        def do_PATCH(self) -> None:
            self.respond()

        def do_DELETE(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = TagFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def tag_session(fixture: TagFixture) -> AsyncGenerator[ClientSession]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "escriptorium_mcp.server"],
        env={"ESCRIPTORIUM_URL": fixture.url, "ESCRIPTORIUM_API_KEY": "fixture-key"},
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        _ = await session.initialize()
        yield session
