"""Owned witness API and binary storage fixture for multipart and ownership checks."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Final, final
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

WITNESSES: Final = "/api/textual-witnesses/"
WITNESS: Final = WITNESSES + "7/"
FILE: Final = "/media/witnesses/reference.txt"


@dataclass(frozen=True, slots=True)
class WitnessFixture:
    """Mutable containers inject native ownership anomalies and record wire effects."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    received: list[tuple[str, str]] = field(default_factory=list)
    uploads: list[bytes] = field(default_factory=list)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)
    disconnect: set[str] = field(default_factory=set)
    binary: bytes = b"\xef\xbb\xbfReference \xc4\x8d\r\nExact bytes\n"
    binary_faults: dict[str, int] = field(default_factory=dict)
    witness: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 7,
            "name": "Reference",
            "owner": "fixture-owner",
            "file": FILE,
            "future": {"zero": 0, "null": None},
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        candidates = [f"{method} {path}", path, route]
        for key in candidates:
            if key in self.failures:
                return self.failures[key], {"detail": "Fixture inaccessible or failed"}
            if key in self.responses:
                return (201 if method == "POST" else 200), self.responses[key]
        if method == "DELETE":
            return 204, None
        collection: JsonValue = (
            self.witness
            if method == "POST"
            else {"count": 1, "next": None, "previous": None, "results": [self.witness]}
        )
        routes: dict[str, JsonValue] = {WITNESS: self.witness, WITNESSES: collection}
        return (
            ((201 if method == "POST" else 200), routes[route])
            if route in routes
            else (404, {"detail": "Unknown fixture route"})
        )


@contextmanager
def witness_fixture() -> Generator[WitnessFixture]:
    fixture = WitnessFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            fixture.received.append((self.command, self.path))
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
            route = urlsplit(self.path).path
            redirect = fixture.redirects.get(self.path, fixture.redirects.get(route))
            if redirect is not None:
                fixture.requests.append((self.command, self.path, body))
                self.send_response(302)
                self.send_header("Location", redirect)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if route == FILE:
                fixture.requests.append((self.command, self.path, body))
                status = fixture.binary_faults.get("status", 200)
                self.send_response(status)
                self.send_header(
                    "Content-Length",
                    str(
                        len(fixture.binary)
                        + fixture.binary_faults.get("extra_length", 0)
                    ),
                )
                self.end_headers()
                _ = self.wfile.write(fixture.binary)
                self.close_connection = True
                return
            status, result = fixture.respond(self.command, self.path, body)
            if f"{self.command} {self.path}" in fixture.disconnect:
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
        fixture = WitnessFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def witness_session(
    fixture: WitnessFixture, books: Path | None = None
) -> AsyncGenerator[ClientSession]:
    environment = {
        "ESCRIPTORIUM_URL": fixture.url,
        "ESCRIPTORIUM_API_KEY": "fixture-key",
    }
    if books is not None:
        environment["ESCRIPTORIUM_BOOKS_ROOT"] = str(books)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "escriptorium_mcp.server"],
        env=environment,
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        _ = await session.initialize()
        yield session
