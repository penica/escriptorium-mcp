import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent
from pydantic import BaseModel
from typing_extensions import override


class ProjectName(BaseModel):
    name: str


class Project(BaseModel):
    id: int
    name: str


class ProjectPage(BaseModel):
    results: list[Project]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.headers.get("Authorization") != "Token fixture-key":
            self.send_error(401)
            return
        if self.path.startswith("/api/projects/"):
            second = "page=2" in self.path
            host = self.headers["Host"]
            body = json.dumps(
                {
                    "count": 2,
                    "next": None if second else f"http://{host}/api/projects/?page=2",
                    "previous": None,
                    "results": [
                        {
                            "id": 2 if second else 1,
                            "name": "Archive",
                            "slug": "archive",
                            "owner": "tester",
                            "created_at": "2026-01-01T00:00:00Z",
                            "updated_at": "2026-01-01T00:00:00Z",
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            _ = self.wfile.write(body)
            return
        if self.path == "/api/documents/1/parts/":
            body = json.dumps(
                {
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [{"pk": 1, "name": "Page", "filename": "page.jpg"}],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)
            return
        if self.path == "/api/documents/1/parts/1/":
            body = b'{"pk":1,"regions":[]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        payload = self.rfile.read(int(self.headers["Content-Length"]))
        name = ProjectName.model_validate_json(payload).name
        if self.path == "/api/projects/":
            body = json.dumps(
                {
                    "id": 3,
                    "name": name,
                    "slug": "new",
                    "owner": "tester",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ).encode()
        else:
            assert self.path == "/api/documents/1/transcriptions/"
            body = json.dumps({"pk": 4, "name": name}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        _ = self.wfile.write(body)

    @override
    def log_message(self, format: str, *args: str) -> None:
        return


@contextmanager
def api_fixture() -> Generator[str, None, None]:
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join()


async def exercise(url: str) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "escriptorium_mcp.server"],
        env={"ESCRIPTORIUM_URL": url, "ESCRIPTORIUM_API_KEY": "fixture-key"},
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        _ = await session.initialize()
        discovered = await session.list_tools()
        assert len(discovered.tools) >= 12
        result = await session.call_tool("list_projects")
        assert not result.is_error
        content = result.content[0]
        assert isinstance(content, TextContent)
        parsed = ProjectPage.model_validate_json(content.text)
        assert [project.id for project in parsed.results] == [1, 2]
        pages = await session.call_tool("list_pages", {"document_id": 1})
        assert not pages.is_error
        regions = await session.call_tool(
            "list_regions", {"document_id": 1, "page_id": 1}
        )
        assert not regions.is_error
        for tool, arguments in (
            ("create_project", {"name": "New project"}),
            ("create_transcription", {"document_id": 1, "name": "Manual"}),
        ):
            created = await session.call_tool(tool, arguments)
            assert not created.is_error
            created_text = created.content[0]
            assert isinstance(created_text, TextContent)
            assert (
                ProjectName.model_validate_json(created_text.text).name
                == arguments["name"]
            )
        invalid = await session.call_tool(
            "get_page",
            {
                "document_id": -1,
                "page_id": 1,
            },
        )
        assert invalid.is_error
        missing = await session.call_tool("get_document", {"document_id": 99})
        assert missing.is_error


def test_protocol_when_connector_reaches_http_fixture() -> None:
    # Given a real HTTP fixture and the unmodified connector package.
    with api_fixture() as url:
        # When the MCP client launches the server and calls its tools.
        # Then discovery, pagination, validation and upstream errors work.
        anyio.run(exercise, url)
