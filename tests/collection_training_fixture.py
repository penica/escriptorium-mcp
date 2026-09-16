"""Owned collection training against paginated, cross-document fixture items."""

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

COLLECTION: Final = "/api/collections/5/"
ITEMS: Final = COLLECTION + "items/"
MODEL: Final = "/api/models/7/"


@dataclass(frozen=True, slots=True)
class CollectionTrainingFixture:
    """Store source identities and request evidence, including failed submissions."""

    url: str
    paginated: bool = True
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    items: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "id": 21,
                "document_id": 4,
                "document_part": 10,
                "transcription_layer": 2,
                "custom": "keep",
            },
            {"id": 22, "document_id": 6, "document_part": 12, "transcription_layer": 3},
        ]
    )
    model: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 7,
            "job": "Recognize",
            "rights": "owner",
            "training": False,
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        key = f"{method} {route}"
        if key in self.failures:
            return self.failures[key], {"detail": "Fixture denied or failed"}
        if key in self.responses:
            return 200, self.responses[key]
        if method == "POST" and route in {
            COLLECTION + "train_recognizer/",
            COLLECTION + "train_segmenter/",
        }:
            return 200, {"status": "ok", "model_id": 9, "custom": "retained"}
        if method != "GET":
            return 405, {"detail": "Unexpected mutation"}
        if route == ITEMS:
            return 200, self.item_page(path)
        details: dict[str, JsonValue] = {
            COLLECTION: {"id": 5, "name": "Fixture", "owner": 1},
            MODEL: self.model,
            "/api/documents/4/": {"pk": 4},
            "/api/documents/6/": {"pk": 6},
            "/api/documents/4/parts/10/": {"pk": 10, "document": 4},
            "/api/documents/6/parts/12/": {"pk": 12, "document": 6},
            "/api/documents/4/transcriptions/2/": {"pk": 2, "archived": False},
            "/api/documents/6/transcriptions/3/": {"pk": 3, "archived": False},
        }
        return (
            (200, details[route])
            if route in details
            else (404, {"detail": "Unknown route"})
        )

    def item_page(self, path: str) -> JsonValue:
        if not self.paginated:
            return self.items
        second = parse_qs(urlsplit(path).query).get("page") == ["2"]
        return {
            "count": len(self.items),
            "next": "?page=2" if len(self.items) > 1 and not second else None,
            "results": self.items[1:] if second else self.items[:1],
        }


@contextmanager
def collection_training_fixture(
    *, paginated: bool = True
) -> Generator[CollectionTrainingFixture]:
    fixture = CollectionTrainingFixture("", paginated)

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
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
        fixture = CollectionTrainingFixture(
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
async def collection_training_session(
    fixture: CollectionTrainingFixture,
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
