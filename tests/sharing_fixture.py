"""Authenticated sharing endpoints preserve grants and record isolated mutations."""

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

PROJECT: Final = "/api/projects/7/"
DOCUMENT: Final = "/api/documents/4/"
GROUP: Final = "/api/groups/2/"


@dataclass(frozen=True, slots=True)
class SharingFixture:
    """Mutable containers model additive grants and configurable wire failures."""

    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    disconnect: set[str] = field(default_factory=set)
    project: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "id": 7,
            "owner": "other-owner",
            "future": {"zero": 0},
            "shared_with_users": [
                {"pk": 3, "username": "existing", "email": "existing@example.invalid"}
            ],
            "shared_with_groups": [{"pk": 5, "name": "Existing group"}],
        }
    )
    document: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 4,
            "project_id": 7,
            "future": None,
            "shared_with_users": [{"pk": 3, "username": "existing"}],
            "shared_with_groups": [{"pk": 5, "name": "Existing group"}],
        }
    )
    group: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "pk": 2,
            "name": "Member group",
            "owner": 99,
            "users": [{"pk": 1, "username": "caller"}],
        }
    )

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        if path in self.failures:
            return self.failures[path], {
                "detail": "Fixture denied or ambiguous failure"
            }
        resources: dict[str, dict[str, JsonValue]] = {
            PROJECT: self.project,
            DOCUMENT: self.document,
            GROUP: self.group,
        }
        if method == "GET" and path in resources:
            return 200, resources[path]
        if method == "POST" and path in {PROJECT + "share/", DOCUMENT + "share/"}:
            assert isinstance(body, dict)
            resource = resources[path.removesuffix("share/")]
            field_name = (
                "shared_with_groups" if "group" in body else "shared_with_users"
            )
            grants = resource[field_name]
            assert isinstance(grants, list)
            new: JsonValue = (
                {"pk": 2, "name": "Member group"}
                if "group" in body
                else {"pk": 8, "username": body["user"], "email": "new@example.invalid"}
            )
            if new not in grants:
                grants.append(new)
            return 201, resource
        return 404, {"detail": "Unknown fixture route"}


@contextmanager
def sharing_fixture() -> Generator[SharingFixture]:
    fixture = SharingFixture("")

    @final
    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
            if self.path in fixture.disconnect:
                self.close_connection = True
                return
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
        fixture = SharingFixture(f"http://127.0.0.1:{server.server_port}/")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def sharing_session(fixture: SharingFixture) -> AsyncGenerator[ClientSession]:
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
