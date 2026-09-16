"""Isolated collection API exposes membership state and configurable HTTP behavior."""

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

COLLECTIONS: Final = "/api/collections/"
COLLECTION: Final = COLLECTIONS + "7/"
ITEMS: Final = COLLECTION + "items/"
DOC: Final = "/api/documents/4/"
OTHER_DOC: Final = "/api/documents/8/"


@dataclass(frozen=True, slots=True)
class CollectionFixture:
    """Mutable containers record calls, alter responses and model saved links."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    received: list[tuple[str, str]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)
    disconnect: set[str] = field(default_factory=set)
    collection: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "id": 7,
            "name": "Research",
            "default_transcriptions": {"4": 2},
            "owner": "fixture-owner",
            "updated_at": "2026-09-16T10:00:00Z",
            "future": {"zero": 0, "null": None},
        }
    )
    items: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "id": 1,
                "document_id": 4,
                "document_part": 11,
                "transcription_layer": 2,
                "part_name": "First",
                "document_name": "Book A",
                "thumbnail": None,
                "part_order": 0,
                "future": False,
            },
            {
                "id": 2,
                "document_id": 8,
                "document_part": 12,
                "transcription_layer": 19,
                "part_name": "Second",
                "document_name": "Book B",
                "thumbnail": "/thumb.jpg",
                "part_order": 1,
            },
        ]
    )
    source_records: dict[str, JsonValue] = field(
        default_factory=lambda: {
            DOC: {"pk": 4},
            OTHER_DOC: {"pk": 8},
            DOC + "parts/11/": {"pk": 11},
            OTHER_DOC + "parts/12/": {"pk": 12},
            DOC + "transcriptions/2/": {"pk": 2, "archived": False},
            OTHER_DOC + "transcriptions/19/": {"pk": 19, "archived": False},
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        failure_key = f"{method} {path}"
        if (
            failure_key in self.failures
            or path in self.failures
            or route in self.failures
        ):
            return self.failures.get(
                failure_key, self.failures.get(path, self.failures.get(route, 500))
            ), {"detail": "Fixture failure after possible partial write"}
        if path in self.responses:
            return 200, self.responses[path]
        if route in self.responses:
            return 200, self.responses[route]
        if method in {"POST", "PATCH"}:
            assert isinstance(body, dict)
            for key in ("name", "default_transcriptions"):
                if key in body:
                    self.collection[key] = body[key]
            if "items_to_save" in body:
                items = body["items_to_save"]
                assert isinstance(items, list)
                self.items[:] = items
            return (201 if method == "POST" else 200), self.collection
        if method == "DELETE":
            self.collection.clear()
            self.items.clear()
            return 204, None
        routes: dict[str, JsonValue] = {
            COLLECTIONS: {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [self.collection],
            },
            COLLECTION: self.collection,
            ITEMS: {"count": len(self.items), "next": None, "results": self.items},
            **self.source_records,
        }
        return (200, routes[route]) if route in routes else (404, {"detail": "Unknown"})


@contextmanager
def collection_fixture() -> Generator[CollectionFixture]:
    fixture = CollectionFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            fixture.received.append((self.command, self.path))
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            route = urlsplit(self.path).path
            redirect = fixture.redirects.get(self.path, fixture.redirects.get(route))
            if redirect is not None:
                fixture.requests.append((self.command, self.path, body))
                self.send_response(302)
                self.send_header("Location", redirect)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status, result = fixture.respond(self.command, self.path, body)
            if (
                f"{self.command} {self.path}" in fixture.disconnect
                or self.path in fixture.disconnect
                or route in fixture.disconnect
            ):
                self.close_connection = True
                return
            payload = (
                b""
                if status == 204
                else TypeAdapter[JsonValue](JsonValue).dump_json(result)
            )
            self.send_response(status)
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
        fixture = CollectionFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def collection_session(
    fixture: CollectionFixture,
) -> AsyncGenerator[ClientSession]:
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
