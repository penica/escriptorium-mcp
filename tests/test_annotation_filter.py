from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import anyio
import pytest
from typing_extensions import override

from tests.ontology_fixture import OntologyFixture, invoke, ontology_session


@pytest.mark.parametrize("target", ["image", "text", None])
def test_annotation_filter_when_listed_through_stdio(target: str | None) -> None:
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            paths.append(self.path)
            body = b'[{"pk":3,"name":"Person"}]'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            _ = self.wfile.write(body)

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    async def exercise(url: str) -> None:
        async with ontology_session(OntologyFixture(url)) as session:
            result = await invoke(
                session,
                "list_annotation_taxonomies",
                {"document_id": 7, "target": target},
            )
            assert result == {"pk": 3, "name": "Person"}

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            anyio.run(exercise, f"http://127.0.0.1:{server.server_port}/")
        finally:
            server.shutdown()
            thread.join()
    suffix = f"?target={target}" if target else ""
    assert paths == [f"/api/documents/7/taxonomies/annotations/{suffix}"]
