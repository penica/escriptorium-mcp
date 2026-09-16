"""Alignment API fixture records direct file uploads and optional monitoring."""

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
LAYER: Final = DOC + "transcriptions/2/"
PARTS: Final = DOC + "parts/"
ALIGN: Final = DOC + "align/"
FORCED: Final = DOC + "forced_align/"
GROUPS: Final = DOC + "task_groups/"
WITNESS: Final = "/api/textual-witnesses/7/"
MODEL: Final = "/api/models/8/"


def alignment_job(changes: dict[str, JsonValue] | None = None) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "transcription": 2,
        "witness": {"kind": "existing", "witness_id": 7},
        "layer_name": "Aligned",
        "acknowledge_target_reuse": True,
    }
    result.update(changes or {})
    return result


@dataclass(frozen=True, slots=True)
class AlignmentFixture:
    """Mutable containers model scopes, uploads, accepted submissions and failures."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    uploads: list[bytes] = field(default_factory=list)
    queued_pages: list[JsonValue] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    document: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 4,
            "valid_block_types": [{"pk": 3, "name": "Main"}],
        }
    )
    layer: dict[str, JsonValue] = field(
        default_factory=lambda: {"pk": 2, "name": "Source", "archived": False}
    )
    model: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 8,
            "job": "Recognize",
            "rights": "public",
            "training": True,
        }
    )
    groups_before: list[JsonValue] = field(
        default_factory=lambda: [{"pk": 1, "method": "core.tasks.align"}]
    )
    groups_after: list[JsonValue] = field(
        default_factory=lambda: [
            {"pk": 1, "method": "core.tasks.align"},
            {"pk": 2, "method": "core.tasks.align", "custom": "keep"},
        ]
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        key = f"{method} {route}"
        if route == GROUPS:
            key = "after" if any(m == "POST" for m, _, _ in self.requests) else "before"
        if key in self.failures:
            if method == "POST" and route == FORCED and self.failures[key] == 500:
                self.queued_pages.append(10)
            return self.failures[key], {"detail": "Fixture denied or invalid selection"}
        if key in self.responses:
            return 200, self.responses[key]
        if method == "POST":
            return self.submit(route, body)
        if method != "GET":
            return 405, {"detail": "Unexpected method"}
        return self.read(route, path, key)

    def submit(self, route: str, body: JsonValue) -> tuple[int, JsonValue]:
        if route == FORCED:
            assert isinstance(body, dict)
            if body["transcription"] != 2:
                return 400, {"detail": "Transcription does not belong to document"}
            pages = body.get("parts", [10, 11])
            assert isinstance(pages, list)
            self.queued_pages.extend(pages)
            return 200, {"status": "success"}
        return (
            (200, {"status": "ok"})
            if route == ALIGN
            else (405, {"detail": "Unexpected write"})
        )

    def read(self, route: str, path: str, key: str) -> tuple[int, JsonValue]:
        if route == PARTS:
            second = parse_qs(urlsplit(path).query).get("page") == ["2"]
            return 200, {
                "count": 2,
                "next": None if second else self.url.rstrip("/") + PARTS + "?page=2",
                "results": [{"pk": 11}] if second else [{"pk": 10}],
            }
        if route == GROUPS:
            groups = self.groups_after if key == "after" else self.groups_before
            return 200, {"count": len(groups), "next": None, "results": groups}
        details: dict[str, JsonValue] = {
            DOC: self.document,
            LAYER: self.layer,
            MODEL: self.model,
            WITNESS: {"pk": 7, "name": "Reference", "owner": "fixture"},
        }
        return (
            (200, details[route])
            if route in details
            else (404, {"detail": "Unknown route"})
        )


@contextmanager
def alignment_fixture() -> Generator[AlignmentFixture]:
    fixture = AlignmentFixture("")

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
        fixture = AlignmentFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def alignment_session(fixture: AlignmentFixture) -> AsyncGenerator[ClientSession]:
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
