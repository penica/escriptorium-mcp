"""Isolated import API records JSON, multipart and task-group discovery requests."""

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
IMPORT: Final = DOC + "import/"
LAYER: Final = DOC + "transcriptions/2/"
GROUPS: Final = DOC + "task_groups/"
METHOD: Final = "imports.tasks.document_import"


@dataclass(frozen=True, slots=True)
class ImportFixture:
    """Mutable containers capture writes and configurable upstream failures."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    uploads: list[bytes] = field(default_factory=list)
    disconnect: set[str] = field(default_factory=set)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    document: dict[str, JsonValue] = field(default_factory=lambda: {"pk": 4})
    layer: dict[str, JsonValue] = field(
        default_factory=lambda: {"pk": 2, "name": "manual", "archived": False}
    )
    groups_before: list[JsonValue] = field(
        default_factory=lambda: [{"pk": 1, "method": METHOD}]
    )
    groups_after: list[JsonValue] = field(
        default_factory=lambda: [
            {"pk": 1, "method": METHOD},
            {"pk": 2, "method": METHOD, "custom": "retained"},
        ]
    )
    reports: list[JsonValue] = field(default_factory=list)

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        key = route
        if route == GROUPS:
            submitted = any(method == "POST" for method, _, _ in self.requests)
            key = "after" if submitted else "before"
        if key in self.failures:
            return self.failures[key], {"detail": "Fixture denied or invalid source"}
        if key in self.responses:
            return 200, self.responses[key]
        mutations: dict[str, tuple[int, JsonValue]] = {
            IMPORT: (201, {"status": "ok"}),
            DOC + "cancel_import/": (200, {"status": "canceled"}),
            DOC + "imports/": (200, {"status": "ok"}),
        }
        if method == "POST" and route in mutations:
            return mutations[route]
        if method != "GET":
            return 405, {"detail": "Unexpected mutation"}
        if route == GROUPS:
            rows = self.groups_after if key == "after" else self.groups_before
            return 200, {"count": len(rows), "next": None, "results": rows}
        details: dict[str, JsonValue] = {
            DOC: self.document,
            LAYER: self.layer,
            GROUPS + "2/": {"pk": 2, "method": METHOD},
            "/api/tasks/": {
                "count": len(self.reports),
                "next": None,
                "results": self.reports,
            },
        }
        return (
            (200, details[route])
            if route in details
            else (404, {"detail": "Unknown fixture route"})
        )


@contextmanager
def import_fixture() -> Generator[ImportFixture]:
    fixture = ImportFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            multipart = self.headers.get("Content-Type", "").startswith("multipart/")
            if multipart:
                fixture.uploads.append(raw)
            body = (
                TypeAdapter[JsonValue](JsonValue).validate_json(raw)
                if raw and not multipart
                else None
            )
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
        fixture = ImportFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def import_session(fixture: ImportFixture) -> AsyncGenerator[ClientSession]:
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
