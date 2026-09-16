"""Authenticated native download fixture with controllable metadata and byte streams."""

import os
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final, final

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

FP: Final = "0123456789abcdef0123456789abcdef"
OTHER_FP: Final = "fedcba9876543210fedcba9876543210"
COLLECTION: Final = "/api/downloads/"
DETAIL: Final = COLLECTION + FP + "/"
FILE: Final = DETAIL + "file/"
BINARY: Final = bytes(range(256)) * 2048


def metadata(fingerprint: str = FP) -> dict[str, JsonValue]:
    return {
        "fingerprint": fingerprint,
        "label": "Research export",
        "mime_type": "application/zip",
        "file_size": len(BINARY),
        "created_at": "2026-09-16T09:00:00Z",
        "expires_at": None,
        "accessed_at": None,
        "accessed_count": 0,
        "task_report_id": None,
        "file_url": "https://untrusted.invalid/private",
        "is_expired": False,
        "future_field": "retained",
    }


@dataclass(frozen=True, slots=True)
class DownloadFixture:
    url: str
    requests: list[tuple[str, str]] = field(default_factory=list)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    detail: dict[str, JsonValue] = field(default_factory=metadata)
    binary: list[bytes] = field(default_factory=lambda: [BINARY])


@contextmanager
def download_fixture() -> Generator[DownloadFixture]:
    fixture = DownloadFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            fixture.requests.append((self.command, self.path))
            if self.path in fixture.redirects:
                self.send_response(302)
                self.send_header("Location", fixture.redirects[self.path])
                self.end_headers()
                return
            status = fixture.failures.get(self.path, 200)
            if status != 200:
                self.send_json(status, {"detail": "Fixture denied or absent"})
                return
            if self.command == "DELETE":
                self.send_response(204)
                self.end_headers()
                return
            if self.path == FILE:
                self.send_binary()
                return
            details: dict[str, JsonValue] = {
                DETAIL: fixture.detail,
                COLLECTION: {"count": 1, "next": None, "results": [fixture.detail]},
                **fixture.responses,
            }
            if self.path in details:
                self.send_json(200, details[self.path])
                return
            self.send_json(404, {"detail": "Unknown fixture route"})

        def send_json(self, status: int, result: JsonValue) -> None:
            payload = TypeAdapter[JsonValue](JsonValue).dump_json(result)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

        def send_binary(self) -> None:
            payload = b"".join(fixture.binary)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Length",
                fixture.headers.get("Content-Length", str(len(payload))),
            )
            self.end_headers()
            for offset in range(0, len(payload), 8192):
                _ = self.wfile.write(payload[offset : offset + 8192])
            self.close_connection = True

        def do_GET(self) -> None:
            self.respond()

        def do_DELETE(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = DownloadFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def download_session(fixture: DownloadFixture) -> AsyncGenerator[ClientSession]:
    env = {"ESCRIPTORIUM_URL": fixture.url, "ESCRIPTORIUM_API_KEY": "fixture-key"}
    books = os.environ.get("ESCRIPTORIUM_BOOKS_ROOT")
    if books:
        env["ESCRIPTORIUM_BOOKS_ROOT"] = books
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "escriptorium_mcp.server"],
        env=env,
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        _ = await session.initialize()
        yield session
