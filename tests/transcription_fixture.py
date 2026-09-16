"""Scoped text API fixture with recorded wire requests and configurable failures."""

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
from mcp_types import CallToolResult
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

DOC: Final = "/api/documents/4/"
PAGE: Final = DOC + "parts/10/"
TEXTS: Final = PAGE + "transcriptions/"
LAYER: Final = DOC + "transcriptions/2/"


@dataclass(frozen=True, slots=True)
class TranscriptionFixture:
    """Accumulate requests and stored rows to observe partial writes and clearing."""

    url: str
    paginated: bool = False
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    records: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "pk": 91,
                "line": 11,
                "transcription": 2,
                "content": "old",
                "graphs": [],
                "avg_confidence": 0.0,
                "versions": [{"content": "history"}],
            },
            {"pk": 92, "line": 12, "transcription": 2, "content": "č"},
        ]
    )
    layer: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 2,
            "name": "manual",
            "archived": False,
            "avg_confidence": None,
            "comments": None,
        }
    )
    stats: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "line_count": 0,
            "characters": [{"char": "č", "frequency": 0}],
        }
    )

    def collection(self, path: str, rows: list[JsonValue]) -> JsonValue:
        if not self.paginated:
            return rows
        query = parse_qs(urlsplit(path).query)
        second = query.get("page") == ["2"]
        return {
            "count": len(rows),
            "next": None
            if second
            else self.url.rstrip("/") + urlsplit(path).path + "?page=2",
            "results": rows[1:] if second else rows[:1],
        }

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        if method != "GET":
            return self.mutate(method, route, body)
        if route in self.failures:
            return self.failures[route], {"detail": "Fixture denied or unavailable"}
        collections: dict[str, list[JsonValue]] = {
            DOC + "transcriptions/": [self.layer, {"pk": 3, "name": "review"}],
            PAGE + "lines/": [{"pk": 11}, {"pk": 12}],
            TEXTS: self.records,
        }
        if route in collections:
            return 200, self.collection(path, collections[route])
        details: dict[str, JsonValue] = {
            PAGE: {"pk": 10, "document": 4},
            DOC: {"pk": 4},
            LAYER: self.layer,
            LAYER + "stats/": self.stats,
            LAYER + "parts_by_char/": {
                "parts": [{"document_part_id": 10, "frequency": 0}]
            },
        }
        if self.records:
            details[TEXTS + "91/"] = self.records[0]
        if route in details:
            return 200, details[route]
        return 404, {"detail": "Unknown fixture route"}

    def mutate(self, method: str, route: str, body: JsonValue) -> tuple[int, JsonValue]:
        single = self.single_mutation(method, route, body)
        if single is not None:
            return single
        if method == "POST" and route == TEXTS + "bulk_create/":
            return 200, {"status": "ok", "lines": [{"pk": 93, "content": "normalized"}]}
        if method == "PUT" and route == TEXTS + "bulk_update/":
            assert isinstance(body, dict)
            lines = body["lines"]
            assert isinstance(lines, list)
            changed: list[JsonValue] = []
            for patch in lines:
                assert isinstance(patch, dict)
                for row in self.records:
                    assert isinstance(row, dict)
                    if row["pk"] == patch["pk"]:
                        row.update(patch)
                        changed.append(row)
                if route in self.failures:
                    return self.failures[route], {
                        "detail": "Later row validation failed"
                    }
            return 200, changed
        if method == "POST" and route == TEXTS + "bulk_delete/":
            assert isinstance(body, dict)
            ids = body["lines"]
            assert isinstance(ids, list)
            for row in self.records:
                assert isinstance(row, dict)
                if row["pk"] in ids:
                    row["content"] = ""
            return 204, None
        return 405, {"detail": "Unexpected mutation"}

    def single_mutation(
        self, method: str, route: str, body: JsonValue
    ) -> tuple[int, JsonValue] | None:
        if method == "PATCH" and route == LAYER:
            assert isinstance(body, dict)
            self.layer.update(body)
            return 200, self.layer
        if route == TEXTS and method == "POST":
            assert isinstance(body, dict)
            row: JsonValue = {"pk": 93, **body}
            self.records.append(row)
            return 201, row
        if route == TEXTS + "91/" and method == "PATCH":
            assert isinstance(body, dict)
            row = self.records[0]
            assert isinstance(row, dict)
            row.update(body)
            return 200, row
        if route == LAYER and method == "DELETE":
            if route in self.failures:
                return self.failures[route], {"detail": "The manual layer is protected"}
            self.layer.update({"archived": True, "name": "archived-manual"})
            return 204, None
        return None


@contextmanager
def transcription_fixture(
    *, paginated: bool = False
) -> Generator[TranscriptionFixture]:
    fixture = TranscriptionFixture("", paginated)

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

        def do_PUT(self) -> None:
            self.respond()

        def do_PATCH(self) -> None:
            self.respond()

        def do_DELETE(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = TranscriptionFixture(
            f"http://127.0.0.1:{server.server_port}/", paginated
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def transcription_session(
    fixture: TranscriptionFixture,
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


def decoded_result(response: CallToolResult) -> JsonValue:
    """Read the full structured value; text blocks flatten top-level lists."""
    assert not response.is_error, response.content
    envelope = TypeAdapter[JsonValue](JsonValue).validate_json(
        response.model_dump_json()
    )
    assert isinstance(envelope, dict)
    structured = envelope["structured_content"]
    assert isinstance(structured, dict)
    return structured["result"]


async def invoke(
    session: ClientSession, name: str, args: dict[str, JsonValue]
) -> JsonValue:
    return decoded_result(await session.call_tool(name, args))
