import json
import shutil
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Final

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent
from typing_extensions import override

UV: Final = shutil.which("uv") or "uv"
WORKER: Final = Path(__file__).resolve().parents[1] / "worker"
SCRIPT: Final = """
import sys
from escriptorium_connector import EscriptoriumConnector
from ontology_native import NativeRequest, execute_native
client = EscriptoriumConnector(base_url=sys.argv[1], api_key='fixture-key')
with client.http:
    print(execute_native(client, NativeRequest.parse_raw(sys.argv[2])))
"""
YAML: Final = b"version: 2\ntypes:\n  lines: []\n"


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, body: bytes, *, methods: str = "GET, OPTIONS") -> None:
        self.send_response(status)
        self.send_header("Allow", methods)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    def do_GET(self) -> None:
        assert self.headers.get("Authorization") == "Token fixture-key"
        if "/9/" in self.path:
            self.reply(404, b"{}")
        elif self.path.endswith("/ontology/export/"):
            self.reply(200, YAML)
        else:
            self.reply(200, b'{"pk": 1}')

    def do_OPTIONS(self) -> None:
        if self.path == "/api/types/line/":
            self.reply(
                200, b'{"actions":{"POST":{"name":{},"color":{"read_only":false}}}}'
            )
        elif "/2/" in self.path:
            self.reply(404, b"{}")
        elif "/3/" in self.path:
            self.reply(403, b"{}")
        else:
            methods = (
                "POST, OPTIONS"
                if self.path.endswith("/import/")
                else "GET, DELETE, OPTIONS"
            )
            self.reply(
                200,
                b'{"actions": {"POST": {"file": {"type": "file"}}}}',
                methods=methods,
            )

    def do_PATCH(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        assert self.path == "/api/types/line/1/"
        assert json.loads(body)["color"] in ("#abcdef", "", None)
        self.reply(200, body)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        assert b'name="file"' in body
        assert YAML in body
        self.reply(200, b'{"warnings": []}')

    @override
    def log_message(self, format: str, *args: str) -> None:
        return


@contextmanager
def fixture_api() -> Generator[str, None, None]:
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join()


def run_native(url: str, request: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            UV,
            "run",
            "--frozen",
            "--project",
            str(WORKER),
            "python",
            "-c",
            SCRIPT,
            url,
            request,
        ],
        cwd=WORKER,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("resource_id", "expected"),
    [(1, "available"), (2, "unavailable_or_hidden"), (3, "denied")],
)
def test_capabilities_distinguish_endpoint_absence_and_denial(
    resource_id: int, expected: str
) -> None:
    with fixture_api() as url:
        result = run_native(
            url,
            json.dumps(
                {
                    "operation": "ontology_native",
                    "action": "capabilities",
                    "scope": "documents",
                    "resource_id": resource_id,
                }
            ),
        )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["endpoints"]["export"]["status"] == expected


def test_missing_parent_is_not_reported_as_unsupported() -> None:
    with fixture_api() as url:
        result = run_native(
            url,
            '{"operation":"ontology_native","action":"capabilities","scope":"documents","resource_id":9}',
        )
    assert result.returncode != 0


def test_native_yaml_export_and_import_preserve_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "ontology.yml"
    with fixture_api() as url:
        request = {
            "operation": "ontology_native",
            "action": "export",
            "scope": "projects",
            "resource_id": 1,
            "destination": str(destination),
        }
        result = run_native(url, json.dumps(request))
        assert result.returncode == 0, result.stderr
        assert destination.read_bytes() == YAML
        conflict = run_native(url, json.dumps(request))
        assert conflict.returncode != 0
        imported = run_native(
            url,
            json.dumps(
                {
                    "operation": "ontology_native",
                    "action": "import",
                    "scope": "documents",
                    "resource_id": 1,
                    "file_path": str(destination),
                }
            ),
        )
        assert imported.returncode == 0, imported.stderr
        assert json.loads(imported.stdout) == {"warnings": []}


@pytest.mark.parametrize("color", ["#abcdef", "", None])
def test_native_mcp_surface_capabilities_colors_and_export(
    tmp_path: Path,
    color: str | None,
) -> None:
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
            caps = await session.call_tool(
                "get_ontology_capabilities", {"scope": "documents", "resource_id": 2}
            )
            assert not caps.is_error, caps.content
            content = caps.content[0]
            assert isinstance(content, TextContent)
            assert json.loads(content.text)["endpoints"]["export"]["http_status"] == 404
            unsupported = await session.call_tool(
                "update_ontology_type_color",
                {"kind": "part", "type_id": 1, "color": "#abcdef"},
            )
            assert unsupported.is_error
            changed = await session.call_tool(
                "update_ontology_type_color",
                {"kind": "line", "type_id": 1, "color": color},
            )
            assert not changed.is_error, changed.content
            changed_content = changed.content[0]
            assert isinstance(changed_content, TextContent)
            assert json.loads(changed_content.text) == {"color": color}
            exported = await session.call_tool(
                "export_native_ontology",
                {
                    "scope": "documents",
                    "resource_id": 1,
                    "destination": str(tmp_path / "native.yml"),
                },
            )
            assert not exported.is_error, exported.content
            assert (tmp_path / "native.yml").read_bytes() == YAML

    with fixture_api() as url:
        anyio.run(exercise, url)
