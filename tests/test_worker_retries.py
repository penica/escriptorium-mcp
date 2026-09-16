from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from typing_extensions import override

from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import call


def test_failed_creation_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            writes.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv(
            "ESCRIPTORIUM_URL", f"http://127.0.0.1:{server.server_port}/"
        )
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        try:
            with pytest.raises(ToolError, match="503"):
                _ = anyio.run(
                    call,
                    ApiRequest(
                        method="POST", route="types/block/", body_json='{"name":"New"}'
                    ),
                )
            assert len(writes) == 1
        finally:
            server.shutdown()
            thread.join()
