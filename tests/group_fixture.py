"""Group REST fixture preserves native creation defects and bounded readback."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final, final
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

CURRENT: Final = "/api/users/current/"
GROUPS: Final = "/api/groups/"
GROUP: Final = GROUPS + "7/"


@dataclass(frozen=True, slots=True)
class GroupFixture:
    """Record raw requests and independently configure accepted data/read failures."""

    url: str
    paginated: bool = True
    current: dict[str, JsonValue] = field(
        default_factory=lambda: {"pk": 2, "is_staff": False, "username": "fixture"}
    )
    group: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 7,
            "name": "Researchers",
            "owner": 2,
            "users": [{"pk": 2}],
            "custom": "retain",
        }
    )
    created: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "pk": 7,
                "name": "Researchers",
                "owner": 2,
                "users": [{"pk": 2}],
                "custom": "accepted",
            }
        ]
    )
    rows: list[JsonValue] = field(
        default_factory=lambda: [
            {"pk": 6, "name": "Unrelated"},
            {"pk": 7, "name": "Straße Researchers", "custom": "keep", "owner": None},
        ]
    )
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    malformed: set[str] = field(default_factory=set)
    disconnect: set[str] = field(default_factory=set)

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        key = f"{method} {route}"
        if key in self.failures:
            return self.failures[key], {"detail": "Fixture inaccessible group"}
        if key in self.responses:
            return 200, self.responses[key]
        if method != "GET":
            return self.mutate(method, route, body)
        if route == CURRENT:
            return 200, self.current
        if route == GROUPS:
            return 200, self.collection(path)
        return (
            (200, self.group)
            if route == GROUP
            else (404, {"detail": "Not a visible group member"})
        )

    def collection(self, path: str) -> JsonValue:
        if not self.paginated:
            return self.rows
        second = parse_qs(urlsplit(path).query).get("page") == ["2"]
        return {
            "count": len(self.rows),
            "next": "?page=2" if not second and len(self.rows) > 1 else None,
            "previous": None,
            "custom": "envelope",
            "results": self.rows[1:] if second else self.rows[:1],
        }

    def mutate(self, method: str, route: str, body: JsonValue) -> tuple[int, JsonValue]:
        if method == "POST" and route == GROUPS:
            return 201, self.created[0]
        if method == "PATCH" and route == GROUP:
            assert isinstance(body, dict)
            self.group.update(body)
            return 200, self.group
        if method == "DELETE" and route == GROUP:
            return 204, None
        return 405, {"detail": "No repair or unsupported mutation route"}


@contextmanager
def group_fixture(*, paginated: bool = True) -> Generator[GroupFixture]:
    fixture = GroupFixture("", paginated)

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
            key = f"{self.command} {urlsplit(self.path).path}"
            if key in fixture.disconnect:
                self.close_connection = True
                return
            payload = (
                b""
                if status == 204
                else TypeAdapter[JsonValue](JsonValue).dump_json(result)
            )
            if key in fixture.malformed:
                payload = b"{invalid JSON"
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
        fixture = GroupFixture(f"http://127.0.0.1:{server.server_port}/", paginated)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def group_session(fixture: GroupFixture) -> AsyncGenerator[ClientSession]:
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
