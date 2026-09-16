import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override


@dataclass(frozen=True, slots=True)
class Request:
    method: str
    path: str
    body: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class Case:
    tool: str
    arguments: dict[str, JsonValue]
    path: str = ""
    method: str = "POST"
    payload: JsonValue = field(default_factory=dict)
    multipart: tuple[bytes, ...] = ()
    preflight: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Fixture:
    url: str
    requests: list[Request]


@contextmanager
def api_fixture() -> Generator[Fixture, None, None]:
    requests: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            if self.headers.get("Authorization") != "Token fixture-key":
                self.send_error(401)
                return
            requests.append(
                Request(
                    self.command,
                    self.path,
                    self.rfile.read(int(self.headers.get("Content-Length", "0"))),
                    self.headers.get("Content-Type", ""),
                )
            )
            deleted = self.command == "DELETE"
            body = b"" if deleted else b'{"pk":81,"status":"queued"}'
            if self.command == "GET":
                reads = {
                    "/api/models/2/": (
                        b'{"pk":2,"job":"Segment","rights":"owner","training":false}'
                    ),
                    "/api/documents/7/parts/11/": b'{"pk":11}',
                    "/api/documents/7/": (
                        b'{"pk":7,"valid_block_types":[{"pk":4},{"pk":1}]}'
                    ),
                    "/api/documents/7/transcriptions/5/": (
                        b'{"pk":5,"archived":false}'
                    ),
                    "/api/documents/7/parts/": (
                        b'{"count":1,"next":null,"results":[{"pk":11}]}'
                    ),
                    "/api/documents/7/parts/11/lines/19/": (
                        b'{"pk":19,"document_part":11,"baseline":[[0,0],[1,1]]}'
                    ),
                    "/api/documents/7/parts/11/blocks/19/": (
                        b'{"pk":19,"document_part":11}'
                    ),
                    "/api/documents/7/parts/11/blocks/": (
                        b'[{"pk":8,"document_part":11}]'
                    ),
                    "/api/documents/7/parts/11/lines/": (
                        b'[{"pk":19,"document_part":11},{"pk":20,"document_part":11}]'
                    ),
                }
                if self.path not in reads:
                    self.send_error(404)
                    return
                body = reads[self.path]
            self.send_response(204 if deleted else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            _ = self.wfile.write(body)

        def do_POST(self) -> None:
            self.respond()

        def do_GET(self) -> None:
            self.respond()

        def do_PATCH(self) -> None:
            self.respond()

        def do_DELETE(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield Fixture(f"http://127.0.0.1:{server.server_port}/", requests)
        finally:
            server.shutdown()
            thread.join()


async def exercise(fixture: Fixture, case: Case) -> None:
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
        result = await session.call_tool(case.tool, case.arguments)
        if not case.path:
            assert result.is_error
            assert fixture.requests == []
            return
        assert not result.is_error, result.content
        assert len(fixture.requests) == len(case.preflight) + 1
        assert (
            tuple((request.method, request.path) for request in fixture.requests[:-1])
            == case.preflight
        )
        request = fixture.requests[-1]
        assert (request.method, request.path) == (case.method, f"/api/{case.path}")
        if case.multipart:
            assert request.content_type.startswith("multipart/form-data; boundary=")
            for fragment in case.multipart:
                assert fragment in request.body
        else:
            assert TypeAdapter(JsonValue).validate_json(request.body) == case.payload
        content = result.content[0]
        assert isinstance(content, TextContent)
        expected = (
            {"status": "success", "http_status": 204}
            if case.method == "DELETE"
            else {"pk": 81, "status": "queued"}
        )
        assert TypeAdapter(JsonValue).validate_json(content.text) == expected
