import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override


@dataclass(frozen=True, slots=True)
class OntologyFixture:
    url: str
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    ontology: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "valid_part_types": [{"pk": 1, "name": "Page"}],
            "valid_block_types": [{"pk": 2, "name": "Text"}],
            "valid_line_types": [
                {"pk": 3, "name": "Body"},
                {"pk": 4, "name": " body "},
            ],
        }
    )
    lines: dict[int, int | None] = field(default_factory=lambda: {11: 3, 12: 3, 13: 99})
    mode: str = "normal"

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        if path == "/api/documents/7/":
            return 200, self.ontology
        if path == "/api/documents/7/modify_ontology/":
            assert isinstance(body, dict)
            for key, ids in body.items():
                assert isinstance(ids, list)
                self.ontology[key] = [
                    {
                        "pk": 81 if pk == 80 else pk,
                        "name": "Added" if pk == 80 else str(pk),
                    }
                    for pk in ids
                ]
            return 200, {"status": "ok"}
        if path.startswith("/api/types/"):
            return self.type_response(method, body)
        collection = self.collection_response(path)
        if collection is not None:
            return 200, collection
        if "/lines/" in path:
            return self.line_response(method, path, body)
        return 404, {"detail": "unknown fixture route"}

    def type_response(self, method: str, body: JsonValue) -> tuple[int, JsonValue]:
        if method == "GET":
            return 200, [{"pk": 3, "name": "Body"}]
        if method == "DELETE":
            return 204, None
        assert isinstance(body, dict)
        return 200, {"pk": 80, "name": body["name"]}

    def collection_response(self, path: str) -> JsonValue:
        if path == "/api/documents/7/parts/":
            return {
                "count": 2,
                "next": f"{self.url}api/documents/7/parts/?page=2",
                "results": [{"pk": 10, "typology": 1}],
            }
        if path == "/api/documents/7/parts/?page=2":
            return {
                "count": 2,
                "next": None,
                "results": [{"pk": 20, "typology": None}],
            }
        if path.endswith("/blocks/"):
            return [{"pk": 21, "typology": {"pk": 2, "name": "Text"}}]
        if path.endswith("/10/lines/"):
            return {
                "count": 2,
                "next": f"{self.url}api/documents/7/parts/10/lines/?page=2",
                "results": [{"pk": 11, "typology": self.lines[11]}],
            }
        if path.endswith("/10/lines/?page=2"):
            return {
                "count": 2,
                "next": None,
                "results": [{"pk": 12, "typology": self.lines[12]}],
            }
        other: dict[str, JsonValue] = {
            "/api/documents/7/parts/20/lines/": [
                {"pk": 13, "typology": self.lines[13]}
            ],
        }
        return other.get(path)

    def line_response(
        self, method: str, path: str, body: JsonValue
    ) -> tuple[int, JsonValue]:
        pk = int(path.rstrip("/").rsplit("/", 1)[1])
        if method == "GET" and self.mode == "conflict" and pk == 11:
            return 200, {"pk": pk, "typology": 4}
        if method == "PATCH":
            if self.mode == "failure" and pk == 12:
                return 500, {"detail": "failed"}
            assert isinstance(body, dict)
            value = body["typology"]
            assert isinstance(value, int) or value is None
            self.lines[pk] = value
        return 200, {"pk": pk, "typology": self.lines[pk]}


@contextmanager
def ontology_fixture(mode: str = "normal") -> Generator[OntologyFixture, None, None]:
    fixture = OntologyFixture("", mode=mode)

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
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
        fixture = OntologyFixture(f"http://127.0.0.1:{server.server_port}/", mode=mode)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def ontology_session(fixture: OntologyFixture) -> AsyncGenerator[ClientSession]:
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


async def invoke(
    session: ClientSession, name: str, args: dict[str, JsonValue]
) -> JsonValue:
    result = await session.call_tool(name, args)
    assert not result.is_error, result.content
    content = result.content[0]
    assert isinstance(content, TextContent)
    return TypeAdapter[JsonValue](JsonValue).validate_json(content.text)
