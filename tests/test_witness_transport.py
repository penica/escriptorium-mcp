"""Private witness transport boundaries and explicit single-attempt requests."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Literal

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from typing_extensions import override

from escriptorium_mcp.api import ApiRequest, Input
from escriptorium_mcp.bridge import call
from tests.download_fixture import download_fixture
from tests.mutation_fixture import Request


class PrivateSingleAttempt(Input):
    operation: Literal["api"] = "api"
    method: Literal["GET"] = "GET"
    route: str = "types/block/"
    single_attempt: Literal[True] = True


def test_private_single_attempt_preserves_http500_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given one retry-eligible failure on an existing worker route.
    with download_fixture() as fixture:
        fixture.failures["/api/types/block/"] = 500
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        # When the private boundary requests one attempt.
        with pytest.raises(ToolError, match="HTTP 500"):
            _ = anyio.run(call, PrivateSingleAttempt())
    # Then the native status survives and no automatic repeat was sent.
    assert fixture.requests == [("GET", "/api/types/block/")]


@dataclass(frozen=True, slots=True)
class TransportFixture:
    url: str
    requests: list[Request]


@contextmanager
def transport_fixture(statuses: tuple[int, ...]) -> Generator[TransportFixture]:
    requests: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            requests.append(
                Request(
                    self.command,
                    self.path,
                    self.rfile.read(int(self.headers.get("Content-Length", "0"))),
                    self.headers.get("Content-Type", ""),
                )
            )
            status = statuses[min(len(requests) - 1, len(statuses) - 1)]
            payload = b"{}" if status == 200 else b""
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

        def do_GET(self) -> None:
            self.respond()

        def do_POST(self) -> None:
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
            yield TransportFixture(f"http://127.0.0.1:{server.server_port}/", requests)
        finally:
            server.shutdown()
            thread.join()


def configure(fixture: TransportFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
    monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")


def test_default_request_omits_private_attempt_flag() -> None:
    # Given an existing caller which never selected the new behavior.
    request = ApiRequest(method="GET", route="types/block/")
    # When the bridge serializes its unchanged private wire payload.
    wire = request.model_dump(exclude_none=True)
    # Then older worker contracts receive no new default field.
    assert "single_attempt" not in wire


def test_default_read_retries_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a transient failure followed by a successful existing read.
    with transport_fixture((500, 200)) as fixture:
        configure(fixture, monkeypatch)
        # When no single-attempt override is supplied.
        result = anyio.run(call, ApiRequest(method="GET", route="types/block/"))
    # Then the established read retry policy remains effective.
    assert result == {}
    assert [row.path for row in fixture.requests] == ["/api/types/block/"] * 2


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
@pytest.mark.parametrize("status", [400, 403, 404, 429, 500, 503])
def test_single_attempt_rejects_empty_http_failure(
    monkeypatch: pytest.MonkeyPatch,
    method: Literal["GET", "POST", "DELETE"],
    status: int,
) -> None:
    # Given an error with an empty body followed by success if repeated.
    with transport_fixture((status, 200)) as fixture:
        configure(fixture, monkeypatch)
        request = ApiRequest(
            method=method, route="textual-witnesses/1/", single_attempt=True
        )
        # When the operation requests exactly one attempt.
        with pytest.raises(ToolError, match=f"HTTP {status}"):
            _ = anyio.run(call, request)
    # Then an empty failure cannot become accepted success or a retry.
    assert len(fixture.requests) == 1


@pytest.mark.parametrize("status", [300, 301, 302, 304, 307, 308])
def test_single_attempt_rejects_redirect_status_without_location(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    # Given a redirect status with no Location header and no response body.
    with transport_fixture((status,)) as fixture:
        configure(fixture, monkeypatch)
        # When requests.is_redirect alone would not identify this response.
        with pytest.raises(ToolError):
            _ = anyio.run(
                call,
                ApiRequest(
                    method="GET", route="textual-witnesses/", single_attempt=True
                ),
            )
    # Then no redirect status is accepted as a bodyless successful result.
    assert len(fixture.requests) == 1


@pytest.mark.parametrize("route", ["textual-witnesses/", "textual-witnesses/27/"])
def test_worker_accepts_only_fixed_witness_route_shapes(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    # Given one native collection or positive-ID detail route.
    with transport_fixture((200,)) as fixture:
        configure(fixture, monkeypatch)
        # When the worker receives the narrowly allowed route.
        result = anyio.run(call, ApiRequest(method="GET", route=route))
    # Then the intended authenticated endpoint is requested unchanged.
    assert result == {}
    assert [row.path for row in fixture.requests] == ["/api/" + route]


@pytest.mark.parametrize(
    "route",
    [
        "textual-witnesses/0/",
        "textual-witnesses/01/",
        "textual-witnesses/word/",
        "textual-witnesses/1/file/",
        "textual-witnesses/../",
        "textual-witnesses/1/?q=x",
        "textual-witnesses/\n",
        "other-hyphens/",
        "textual-witnesses//",
    ],
)
def test_worker_refuses_unregistered_witness_paths(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    # Given an unregistered or ambiguous path under the new prefix.
    with transport_fixture((200,)) as fixture:
        configure(fixture, monkeypatch)
        # When the raw private boundary receives the path.
        with pytest.raises(ToolError):
            _ = anyio.run(call, ApiRequest(method="GET", route=route))
    # Then validation prevents every authenticated HTTP request.
    assert fixture.requests == []


def test_alignment_upload_uses_witness_file_multipart_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given exact UTF-8 witness bytes and a native alignment payload.
    witness = tmp_path / "reference.txt"
    payload = "Witness ž\n".encode()
    _ = witness.write_bytes(payload)
    with transport_fixture((200,)) as fixture:
        configure(fixture, monkeypatch)
        # When the adapter forwards the explicit upload-field selection.
        result = anyio.run(
            call,
            ApiRequest(
                method="POST",
                route="documents/1/align/",
                file_path=witness,
                file_field="witness_file",
                body_json='{"transcription":3}',
                single_attempt=True,
            ),
        )
    # Then one multipart request preserves both the field name and file bytes.
    assert result == {}
    assert len(fixture.requests) == 1
    assert b'name="witness_file"; filename="reference.txt"' in fixture.requests[0].body
    assert payload in fixture.requests[0].body


def test_single_attempt_delete_retains_bodyless_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a successful native deletion with no response body.
    with transport_fixture((204,)) as fixture:
        configure(fixture, monkeypatch)
        # When the guarded operation returns its native success status.
        result = anyio.run(
            call,
            ApiRequest(
                method="DELETE", route="textual-witnesses/1/", single_attempt=True
            ),
        )
    # Then the explicit status is preserved without a verification requery.
    assert result == {"status": "success", "http_status": 204}
    assert len(fixture.requests) == 1
