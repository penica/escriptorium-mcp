"""Isolated project/document API with raw records and scoped tag catalogues."""

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

PROJECTS: Final = "/api/projects/"
DOCUMENTS: Final = "/api/documents/"
PROJECT: Final = PROJECTS + "1/"
DOCUMENT: Final = DOCUMENTS + "4/"
PERSONAL: Final = "/api/tags/project/"


@dataclass(frozen=True, slots=True)
class RecordFixture:
    """Mutable containers expose request evidence and configurable response records."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    project: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "id": 1,
            "slug": "old",
            "name": "Old",
            "guidelines": None,
            "shared_with_users": [{"id": 7, "username": "editor"}],
            "tags": [{"pk": 31, "name": "Personal", "color": "#111111"}],
            "transcription_font": None,
            "effective_transcription_font": "Serif",
            "documents_count": 0,
            "created_at": "2026-09-16T10:00:00Z",
            "future": False,
        }
    )
    document: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 4,
            "name": "Document",
            "project": "old",
            "project_id": 1,
            "project_name": "Old",
            "tags": [{"pk": 11, "name": "Assigned"}],
            "transcription_font": None,
            "effective_transcription_font": "Serif",
            "valid_block_types": [{"pk": 3, "name": "Text", "color": "#abcabc"}],
            "show_confidence_viz": False,
            "parts_count": 0,
            "future": {"empty": None},
            "updated_at": "2026-09-16T10:00:00Z",
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        if route in self.failures:
            return self.failures[route], {"detail": "Fixture permission failure"}
        if path in self.responses:
            return 200, self.responses[path]
        if route in self.responses:
            return 200, self.responses[route]
        if method in {"POST", "PATCH"}:
            return 200, {"saved": body}
        if method != "GET":
            return 405, {"detail": "Unexpected mutation"}
        new_project: JsonValue = {"id": 2, "slug": "new", "name": "New"}
        routes: dict[str, JsonValue] = {
            PROJECT: self.project,
            DOCUMENT: self.document,
            PROJECTS + "2/": new_project,
            PROJECTS: {
                "count": 2,
                "next": None,
                "previous": None,
                "results": [self.project, new_project],
            },
            DOCUMENTS: {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [self.document],
            },
            PERSONAL: {"count": 2, "next": None, "results": [{"pk": 31}, {"pk": 32}]},
            PROJECT + "tags/": [{"pk": 11}],
            PROJECTS + "2/tags/": [{"pk": 21}],
            DOCUMENT + "stats/": {
                "regions": [
                    {
                        "typology_id": None,
                        "typology_name": None,
                        "typology_color": None,
                        "frequency": 0,
                    }
                ],
                "lines": [],
                "image_annotations": [],
                "text_annotations": [],
            },
            DOCUMENT + "part_ids/": [12, 11],
            DOCUMENT + "elements_by_type/": {"parts": []},
        }
        return (200, routes[route]) if route in routes else (404, {"detail": "Unknown"})


@contextmanager
def record_fixture() -> Generator[RecordFixture]:
    fixture = RecordFixture("")

    @final
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

        def do_PATCH(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = RecordFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def record_session(fixture: RecordFixture) -> AsyncGenerator[ClientSession]:
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
