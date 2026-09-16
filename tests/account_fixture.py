"""Isolated self-only/staff account API with observable native mutation requests."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TYPE_CHECKING, Final, final
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

if TYPE_CHECKING:
    from typing import TextIO

USERS: Final = "/api/users/"
CURRENT: Final = USERS + "current/"
SELF: Final = USERS + "1/"
OTHER: Final = USERS + "2/"


@dataclass(frozen=True, slots=True)
class AccountFixture:
    """Mutable containers expose response anomalies and request-side effects."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    received: list[tuple[str, str]] = field(default_factory=list)
    responses: dict[str, JsonValue] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)
    disconnect: set[str] = field(default_factory=set)
    current: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 1,
            "username": "član",
            "email": "owner@example.org",
            "first_name": "Albin",
            "last_name": "",
            "is_staff": False,
            "is_active": True,
            "can_invite": True,
            "last_login": None,
            "date_joined": "2026-09-16T10:00:00Z",
            "future": {"zero": 0},
        }
    )
    other: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 2,
            "username": "Straße",
            "email": "other@example.org",
            "first_name": None,
            "last_name": "Surname",
            "is_staff": False,
            "is_active": False,
            "future": "retained",
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        for key in (f"{method} {path}", path, route):
            if key in self.failures:
                return self.failures[key], {"detail": "Fixture native account error"}
            if key in self.responses:
                return 200, self.responses[key]
        staff = self.current["is_staff"] is True
        if (route == OTHER or method in {"POST", "DELETE"}) and not staff:
            return (404 if route == OTHER else 403), {"detail": "Account access denied"}
        if method == "GET":
            users: list[JsonValue] = (
                [self.current, self.other] if staff else [self.current]
            )
            responses: dict[str, JsonValue] = {
                CURRENT: self.current,
                SELF: self.current,
                OTHER: self.other,
                USERS: {
                    "count": len(users),
                    "next": None,
                    "previous": None,
                    "results": users,
                },
            }
            return (200, responses[route]) if route in responses else (404, None)
        if method == "DELETE":
            return 204, None
        return (201 if method == "POST" else 200), {
            "pk": 2 if route in {USERS, OTHER} else 1,
            "saved": body,
        }


@contextmanager
def account_fixture() -> Generator[AccountFixture]:
    fixture = AccountFixture("")

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
        fixture = AccountFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def account_session(
    fixture: AccountFixture, errlog: "TextIO" = sys.stderr
) -> AsyncGenerator[ClientSession]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "escriptorium_mcp.server"],
        env={"ESCRIPTORIUM_URL": fixture.url, "ESCRIPTORIUM_API_KEY": "fixture-key"},
    )
    async with (
        stdio_client(parameters, errlog=errlog) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        _ = await session.initialize()
        yield session
