"""Scoped metadata wire fixture models association rows and one shared key."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

DOC: Final = "/api/documents/4/"
PAGE: Final = DOC + "parts/10/"
DOCUMENT_METADATA: Final = DOC + "metadata/"
PAGE_METADATA: Final = PAGE + "metadata/"


@dataclass(frozen=True, slots=True)
class MetadataFixture:
    """Accumulate requests, rows and shared-key mutations for observable effects."""

    url: str
    paginated: bool = True
    key: dict[str, JsonValue] = field(
        default_factory=lambda: {"name": "place", "cidoc_id": "P7"}
    )
    rows: dict[int, dict[str, JsonValue]] = field(
        default_factory=lambda: {
            91: {"pk": 91, "value": "same", "custom": "retained"},
            92: {"pk": 92, "value": "same"},
            93: {"pk": 93, "value": "page"},
        }
    )
    document_ids: list[int] = field(default_factory=lambda: [91, 92])
    page_ids: list[int] = field(default_factory=lambda: [93])
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)

    def row(self, identifier: int) -> JsonValue:
        return {**self.rows[identifier], "key": self.key}

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        failure_key = f"{method} {route}"
        if failure_key in self.failures:
            return self.failures[failure_key], {
                "detail": "Fixture denied or conflicting key"
            }
        if failure_key in self.responses:
            return 200, self.responses[failure_key]
        if method == "GET" and route in {DOC, PAGE}:
            return 200, {"pk": 4} if route == DOC else {"pk": 10, "document": 4}
        collection = (
            PAGE_METADATA if route.startswith(PAGE_METADATA) else DOCUMENT_METADATA
        )
        if not route.startswith(collection):
            return 404, {"detail": "Unknown route"}
        ids = self.page_ids if collection == PAGE_METADATA else self.document_ids
        if route == collection:
            return self.collection_response(method, path, body, ids)
        identifier = int(route.removeprefix(collection).strip("/"))
        return (
            self.detail_response(method, identifier, body)
            if identifier in ids
            else (404, {"detail": "Foreign or absent association"})
        )

    def collection_response(
        self, method: str, path: str, body: JsonValue, ids: list[int]
    ) -> tuple[int, JsonValue]:
        if method == "GET":
            rows = [self.row(identifier) for identifier in ids]
            if not self.paginated:
                return 200, rows
            second = parse_qs(urlsplit(path).query).get("page") == ["2"]
            return 200, {
                "count": len(rows),
                "next": self.url.rstrip("/") + urlsplit(path).path + "?page=2"
                if not second and len(rows) > 1
                else None,
                "results": rows[1:] if second else rows[:1],
            }
        if method == "POST":
            assert isinstance(body, dict)
            identifier = max(self.rows, default=90) + 1
            self.rows[identifier] = {"pk": identifier, "value": body["value"]}
            ids.append(identifier)
            return 201, {"pk": identifier, **body}
        return 405, {"detail": "Unsupported method"}

    def detail_response(
        self, method: str, identifier: int, body: JsonValue
    ) -> tuple[int, JsonValue]:
        if method == "GET":
            return 200, self.row(identifier)
        if method == "PATCH":
            assert isinstance(body, dict)
            if "value" in body:
                self.rows[identifier]["value"] = body["value"]
            if "key" in body:
                key = body["key"]
                assert isinstance(key, dict)
                self.key.update(key)
            return 200, self.row(identifier)
        if method == "DELETE":
            del self.rows[identifier]
            ids = self.page_ids if identifier in self.page_ids else self.document_ids
            ids.remove(identifier)
            return 204, None
        return 405, {"detail": "Unsupported method"}


@contextmanager
def metadata_fixture(*, paginated: bool = True) -> Generator[MetadataFixture]:
    fixture = MetadataFixture("", paginated)

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
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
        fixture = MetadataFixture(f"http://127.0.0.1:{server.server_port}/", paginated)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def metadata_session(fixture: MetadataFixture) -> AsyncGenerator[ClientSession]:
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
