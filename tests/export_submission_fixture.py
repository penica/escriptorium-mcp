"""Isolated native export endpoint with observable request and failure state."""

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

DOC: Final = "/api/documents/4/"
EXPORT: Final = DOC + "export/"
LAYER: Final = DOC + "transcriptions/2/"
PARTS: Final = DOC + "parts/"


@dataclass(frozen=True, slots=True)
class ExportFixture:
    """Mutable containers record requests and inject upstream fixture responses."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    disconnect: set[str] = field(default_factory=set)
    document: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 4,
            "name": "Fixture",
            "project": "Project",
            "main_script": None,
            "read_direction": "ltr",
            "line_offset": 0,
            "parts_count": 2,
            "created_at": "2026-09-16T10:00:00Z",
            "updated_at": "2026-09-16T10:00:00Z",
            "valid_block_types": [{"pk": 3, "name": "Main"}, {"pk": 7, "name": "Note"}],
        }
    )
    layer: dict[str, JsonValue] = field(
        default_factory=lambda: {"pk": 2, "name": "manual", "archived": False}
    )
    pages: list[JsonValue] = field(default_factory=lambda: [{"pk": 11}, {"pk": 12}])

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        if route in self.failures:
            return self.failures[route], {"detail": "Fixture denied or disabled format"}
        if path in self.responses:
            return 200, self.responses[path]
        if route in self.responses:
            return 200, self.responses[route]
        if method == "POST" and route == EXPORT:
            return 200, {"status": "ok"}
        if method != "GET":
            return 405, {"detail": "Unexpected mutation"}
        details: dict[str, JsonValue] = {
            DOC: self.document,
            LAYER: self.layer,
            DOC + "transcriptions/": [self.layer],
            PARTS: {"count": len(self.pages), "next": None, "results": self.pages},
            PARTS + "11/": {"pk": 11},
            PARTS + "12/": {"pk": 12},
            DOC + "types/block/": self.document["valid_block_types"],
        }
        return (
            (200, details[route])
            if route in details
            else (404, {"detail": "Unknown fixture route"})
        )


@contextmanager
def export_fixture() -> Generator[ExportFixture]:
    fixture = ExportFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
            if urlsplit(self.path).path in fixture.disconnect:
                self.close_connection = True
                return
            payload = TypeAdapter[JsonValue](JsonValue).dump_json(result)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

        def do_GET(self) -> None:
            self.respond()

        def do_POST(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = ExportFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def export_session(fixture: ExportFixture) -> AsyncGenerator[ClientSession]:
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
