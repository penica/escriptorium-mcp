import hashlib
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent
from pydantic import BaseModel, JsonValue
from typing_extensions import override


class SavedFile(BaseModel):
    path: str
    bytes: int
    sha256: str


class ExportHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        assert self.headers.get("Authorization") == "Token fixture-key"
        data: JsonValue
        if self.path.endswith("/transcriptions/5/"):
            data = {"pk": 5, "name": "Manual"}
        elif self.path.endswith("/parts/"):
            data = {
                "count": 2,
                "next": None,
                "results": [
                    {"pk": 11, "filename": "second.jpg", "order": 1},
                    {"pk": 10, "filename": "first.jpg", "order": 0},
                ],
            }
        elif self.path.endswith("/lines/"):
            data = {
                "count": 2,
                "next": None,
                "results": [
                    {"pk": 1, "order": 1},
                    {"pk": 2, "order": 0},
                ],
            }
        elif self.path.endswith("/transcriptions/"):
            data = {
                "count": 3,
                "next": None,
                "results": [
                    {"line": 1, "transcription": 5, "content": "Second č"},
                    {"line": 2, "transcription": 9, "content": "Other layer"},
                    {"line": 2, "transcription": 5, "content": "First ž"},
                ],
            }
        else:
            self.send_response(200)
            self.send_header("Content-Length", "7")
            self.end_headers()
            _ = self.wfile.write(b"archive")
            return
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    @override
    def log_message(self, format: str, *args: str) -> None:
        return


@contextmanager
def fixture_api() -> Generator[str, None, None]:
    with ThreadingHTTPServer(("127.0.0.1", 0), ExportHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join()


async def exercise_exports(url: str, folder: Path) -> None:
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
        destination = folder / "transcription.txt"
        result = await session.call_tool(
            "export_transcriptions",
            {
                "export": {
                    "document_id": 7,
                    "transcription_id": 5,
                    "destination": str(destination),
                    "file_format": "text",
                }
            },
        )
        assert not result.is_error
        content = result.content[0]
        assert isinstance(content, TextContent)
        saved = SavedFile.model_validate_json(content.text)
        assert (
            destination.read_text(encoding="utf-8")
            == "First ž\nSecond č\n\f\nFirst ž\nSecond č"
        )
        assert saved.sha256 == hashlib.sha256(destination.read_bytes()).hexdigest()
        conflict = await session.call_tool(
            "export_transcriptions",
            {
                "export": {
                    "document_id": 7,
                    "transcription_id": 5,
                    "destination": str(destination),
                    "file_format": "json",
                }
            },
        )
        assert conflict.is_error
        assert destination.read_text(encoding="utf-8").startswith("First ž")
        missing = await session.call_tool(
            "export_transcriptions",
            {
                "export": {
                    "document_id": 7,
                    "transcription_id": 5,
                    "parts": [99],
                    "destination": str(folder / "missing.txt"),
                }
            },
        )
        assert missing.is_error
        assert not (folder / "missing.txt").exists()
        downloaded = await session.call_tool(
            "download_export",
            {
                "export": {
                    "url": url + "export.zip",
                    "destination": str(folder / "export.zip"),
                }
            },
        )
        assert not downloaded.is_error
        assert (folder / "export.zip").read_bytes() == b"archive"
        unsafe = await session.call_tool(
            "download_export",
            {
                "export": {
                    "url": "http://example.invalid/export.zip",
                    "destination": str(folder / "unsafe.zip"),
                }
            },
        )
        assert unsafe.is_error
        assert not (folder / "unsafe.zip").exists()


def test_exports_when_client_calls_real_stdio_server(tmp_path: Path) -> None:
    # Given the real worker, fixture API and isolated destination.
    with fixture_api() as url:
        # When exports and downloads are requested through MCP.
        # Then ordering, layer selection, checksums and refusal paths hold.
        anyio.run(exercise_exports, url, tmp_path)
