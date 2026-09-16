"""Training submissions and monitoring reads exposed through a local HTTP API."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Literal
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override


@dataclass(frozen=True, slots=True)
class TrainingFixture:
    """Record calls and allow each scenario to configure model/group metadata."""

    url: str
    scenario: Literal["normal", "before_failure", "after_failure", "post_failure"]
    model: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 7,
            "job": "Recognize",
            "rights": "owner",
            "training": False,
        }
    )
    groups_before: list[JsonValue] = field(
        default_factory=lambda: [
            {"pk": 2, "method": "core.tasks.train"},
        ]
    )
    groups_after: list[JsonValue] = field(
        default_factory=lambda: [
            {"pk": 2, "method": "core.tasks.train"},
            {"pk": 3, "method": "core.tasks.train"},
        ]
    )
    reports: list[JsonValue] = field(default_factory=list)
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        if path == "/api/models/7/" and method == "GET":
            return 200, self.model
        if path == "/api/documents/4/task_groups/" and method == "GET":
            reads = sum(route == path for _method, route, _body in self.requests)
            failed = (reads == 1 and self.scenario == "before_failure") or (
                reads > 1 and self.scenario == "after_failure"
            )
            if failed:
                return 403, {"detail": "Fixture monitoring denied"}
            groups = self.groups_before if reads == 1 else self.groups_after
            return 200, {"count": len(groups), "next": None, "results": groups}
        if (
            path in {"/api/documents/4/train/", "/api/documents/4/segtrain/"}
            and method == "POST"
        ):
            if self.scenario == "post_failure":
                return 400, {
                    "status": "error",
                    "error": {"parts": ["Fixture invalid page"]},
                }
            return 200, {"status": "ok"}
        return self.report_response(path)

    def report_response(self, path: str) -> tuple[int, JsonValue]:
        route = urlsplit(path).path
        if route == "/api/documents/4/":
            return 200, {"pk": 4}
        if route == "/api/documents/4/task_groups/2/":
            return 200, {"pk": 2, "method": "core.tasks.train"}
        if route == "/api/tasks/":
            return 200, {
                "count": len(self.reports),
                "next": None,
                "results": self.reports,
            }
        return 404, {"detail": "Unknown fixture route"}


@contextmanager
def training_fixture(
    scenario: Literal[
        "normal", "before_failure", "after_failure", "post_failure"
    ] = "normal",
) -> Generator[TrainingFixture, None, None]:
    fixture = TrainingFixture("", scenario)

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
        fixture = TrainingFixture(f"http://127.0.0.1:{server.server_port}/", scenario)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def training_session(fixture: TrainingFixture) -> AsyncGenerator[ClientSession]:
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
