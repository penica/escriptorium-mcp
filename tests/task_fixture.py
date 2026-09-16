"""HTTP-level task API fixture with recorded requests and two-page responses."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override


def report(
    pk: int, state: int, method: str = "core.tasks.train"
) -> dict[str, JsonValue]:
    return {
        "pk": pk,
        "document": 7,
        "document_part": "Page label",
        "workflow_state": state,
        "label": "Fixture task",
        "messages": "fixture diagnostic",
        "queued_at": "2026-09-16T01:00:00Z",
        "started_at": None,
        "done_at": None,
        "method": method,
        "user": 2,
    }


@dataclass(frozen=True, slots=True)
class TaskFixture:
    """Accumulate request evidence while retaining immutable fixture configuration."""

    url: str
    rows: list[dict[str, JsonValue]]
    status: int = 200
    plain_list: bool = False
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        if self.status != 200:
            return self.status, {"detail": "Fixture failure"}
        parsed = urlsplit(path)
        if method == "POST" and parsed.path in {
            "/api/documents/7/cancel_tasks/",
            "/api/documents/7/cancel_import/",
        }:
            return 200, {"status": "canceled"}
        if method != "GET":
            return 405, {"detail": "Method not allowed"}
        if parsed.path == "/api/tasks/":
            if self.plain_list:
                return 200, list[JsonValue](self.rows)
            query = parse_qs(parsed.query)
            page = int(query.get("page", ["1"])[0])
            following = None
            if page == 1 and len(self.rows) > 1:
                query["page"] = ["2"]
                following = f"{self.url}api/tasks/?{urlencode(query, doseq=True)}"
            rows: list[JsonValue] = list(self.rows[:1] if page == 1 else self.rows[1:])
            return 200, {"count": len(self.rows), "next": following, "results": rows}
        return self.document_response(parsed.path)

    def document_response(self, path: str) -> tuple[int, JsonValue]:
        if path == "/api/documents/7/":
            return 200, {"pk": 7, "name": "Fixture document"}
        if path == "/api/documents/tasks/":
            return 200, {"count": 1, "next": None, "results": [{"pk": 7}]}
        group: dict[str, JsonValue] = {
            "pk": 4,
            "method": "core.tasks.train",
            "created_at": "2026-09-16T01:00:00Z",
            "created_by": "fixture",
            "page_count": 1,
            "tasks": [{"workflow_state": "Finished", "count": 1}],
        }
        if path == "/api/documents/7/task_groups/":
            return 200, {"count": 1, "next": None, "results": [group]}
        if path == "/api/documents/7/task_groups/4/":
            return 200, group
        return 404, {"detail": "Unknown fixture route"}


@contextmanager
def task_fixture(
    rows: list[dict[str, JsonValue]], status: int = 200, *, plain_list: bool = False
) -> Generator[TaskFixture, None, None]:
    fixture = TaskFixture("", rows, status, plain_list)

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
        fixture = TaskFixture(
            f"http://127.0.0.1:{server.server_port}/", rows, status, plain_list
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def task_session(fixture: TaskFixture) -> AsyncGenerator[ClientSession]:
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
