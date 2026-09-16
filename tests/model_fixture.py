"""Model API and binary downloads served over local HTTP for protocol tests."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

from tests.mutation_fixture import Request


@dataclass(frozen=True, slots=True)
class ModelFixture:
    """Retain request evidence and mutable model data for individual scenarios."""

    url: str
    model: dict[str, JsonValue]
    binary_status: int = 200
    length_extra: int = 0
    binary: bytes = b"fixture-model-weights"
    requests: list[Request] = field(default_factory=list)

    def response(self, method: str, path: str) -> tuple[int, JsonValue]:
        route = urlsplit(path).path
        if route == "/api/models/":
            if method == "GET":
                return 200, {"count": 1, "next": None, "results": [self.model]}
            return 201, self.model
        if route == "/api/models/7/":
            return (204, None) if method == "DELETE" else (200, self.model)
        return 404, {"detail": "Unknown fixture endpoint"}


@contextmanager
def model_fixture(
    *,
    binary_status: int = 200,
    length_extra: int = 0,
) -> Generator[ModelFixture, None, None]:
    fixture = ModelFixture("", {})

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            fixture.requests.append(
                Request(
                    self.command,
                    self.path,
                    self.rfile.read(int(self.headers.get("Content-Length", "0"))),
                    self.headers.get("Content-Type", ""),
                )
            )
            binary = self.path.startswith("/media/")
            if binary:
                status = fixture.binary_status
                payload = fixture.binary
            else:
                status, result = fixture.response(self.command, self.path)
                payload = (
                    b""
                    if status == 204
                    else TypeAdapter[JsonValue](JsonValue).dump_json(result)
                )
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "http://other.invalid/weights")
            self.send_header(
                "Content-Type",
                "application/octet-stream" if binary else "application/json",
            )
            self.send_header(
                "Content-Length",
                str(len(payload) + (fixture.length_extra if binary else 0)),
            )
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
        url = f"http://127.0.0.1:{server.server_port}/"
        model: dict[str, JsonValue] = {
            "pk": 7,
            "name": "Fixture model",
            "rights": "owner",
            "training": False,
            "file": url + "media/models/hash/current.safetensors",
            "file_size": 21,
            "job": "Segment",
            "documents": [4, 8],
            "versions": [
                {
                    "revision": "revision-1",
                    "data": {
                        "file": "models/hash/epoch=01.ckpt",
                        "training_epoch": 1,
                    },
                }
            ],
        }
        fixture = ModelFixture(url, model, binary_status, length_extra)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def model_session(
    fixture: ModelFixture, books_root: Path | None = None
) -> AsyncGenerator[ClientSession]:
    environment = {
        "ESCRIPTORIUM_URL": fixture.url,
        "ESCRIPTORIUM_API_KEY": "fixture-key",
    }
    if books_root is not None:
        environment["ESCRIPTORIUM_BOOKS_ROOT"] = str(books_root)
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
