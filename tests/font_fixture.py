"""Native font metadata and capability-aware project/document assignment fixture."""

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

FONTS: Final = "/api/fonts/"
FONT: Final = FONTS + "3/"
PROJECTS: Final = "/api/projects/"
PROJECT: Final = PROJECTS + "1/"
DOCUMENTS: Final = "/api/documents/"
DOCUMENT: Final = DOCUMENTS + "4/"


@dataclass(frozen=True, slots=True)
class FontFixture:
    """Native values and request records are retained in mutable containers."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    received: list[tuple[str, str]] = field(default_factory=list)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)
    font: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 3,
            "name": "Native Font",
            "url": "https://storage.invalid/font.woff2",
            "size_adjust": 0,
            "ascent_override": None,
            "descent_override": 0,
            "line_height": 1.25,
            "input_height": None,
            "input_padding_top": 0,
            "input_padding_bottom": 0.1,
            "input_margin_top": -0.25,
            "input_margin_bottom": -0.5,
            "input_vertical_align": "",
            "future": {"kept": True},
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        for key in (f"{method} {path}", path, route):
            if key in self.failures:
                return self.failures[key], {"detail": "Fixture unavailable or denied"}
            if key in self.responses:
                return 200, self.responses[key]
        if method == "OPTIONS":
            actions: dict[str, JsonValue] = {
                key: {"transcription_font": {"read_only": False, "required": False}}
                for key in ("POST", "PUT", "PATCH")
            }
            return 200, {"actions": actions}
        if method in {"POST", "PATCH"}:
            return (201 if method == "POST" else 200), {"saved": body}
        project: JsonValue = {
            "id": 1,
            "name": "Project",
            "slug": "project",
            "transcription_font": 3,
        }
        document: JsonValue = {
            "pk": 4,
            "name": "Document",
            "project": "project",
            "project_id": 1,
            "transcription_font": 3,
            "effective_transcription_font": self.font,
        }
        routes: dict[str, JsonValue] = {
            FONTS: {"count": 1, "next": None, "previous": None, "results": [self.font]},
            FONT: self.font,
            PROJECT: project,
            DOCUMENT: document,
            PROJECTS: {"count": 1, "next": None, "results": [project]},
            DOCUMENTS: {"count": 1, "next": None, "results": [document]},
        }
        return (200, routes[route]) if route in routes else (404, {"detail": "Unknown"})


@contextmanager
def font_fixture() -> Generator[FontFixture]:
    fixture = FontFixture("")

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
            payload = TypeAdapter[JsonValue](JsonValue).dump_json(result)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

        def do_GET(self) -> None:
            self.respond()

        def do_OPTIONS(self) -> None:
            self.respond()

        def do_POST(self) -> None:
            self.respond()

        def do_PATCH(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = FontFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def font_session(fixture: FontFixture) -> AsyncGenerator[ClientSession]:
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
