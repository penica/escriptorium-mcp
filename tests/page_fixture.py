"""Wire-level page fixture with bounded redirects and observable mutations."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final
from urllib.parse import parse_qs, urlencode, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

DOC: Final = "/api/documents/4/"
PARTS: Final = DOC + "parts/"
PAGE: Final = PARTS + "10/"


@dataclass(frozen=True, slots=True)
class PageFixture:
    """Store fixture rows and requests so writes and retries remain observable."""

    url: str
    paginated: bool = False
    prefix: str = ""
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    locations: dict[str, str] = field(default_factory=dict)
    uploads: list[bytes] = field(default_factory=list)
    details: dict[str, JsonValue] = field(default_factory=dict)
    rows: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "pk": pk,
                "document": 4,
                "order": order,
                "name": f"page-{pk}",
                "original_filename": f"scan-{pk}.png",
                "source": "archive",
                "comments": "old",
                "image": {"uri": f"/media/{pk}.png", "size": [100, 80]},
                "image_file_size": 123,
                "max_avg_confidence": None,
                "regions": [
                    {"pk": 21, "locked": True, "box": [[1, 2], [3, 2], [3, 4]]}
                ],
                "lines": [{"pk": 11, "baseline": [[1, 2], [3, 2]], "mask": None}],
                "metadata": [{"key": "unmodified", "value": "native"}],
            }
            for order, pk in enumerate((10, 20, 30, 40, 50))
        ]
    )

    def collection(self, path: str) -> JsonValue:
        if not self.paginated:
            return self.rows
        query = parse_qs(urlsplit(path).query)
        second = query.get("page") == ["2"]
        query["page"] = ["2"]
        return {
            "count": len(self.rows),
            "previous": None,
            "next": None
            if second
            else self.locations.get(
                "next",
                self.url.rstrip("/") + PARTS + "?" + urlencode(query, doseq=True),
            ),
            "results": self.rows[1:] if second else self.rows[:1],
        }

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path.removeprefix(self.prefix)
        if method != "GET":
            return self.mutate(method, route, body)
        if route in self.failures:
            return self.failures[route], {"error": "Out of bounds."}
        if route == PARTS + "byorder/" or route in self.locations:
            return 302, None
        details: dict[str, JsonValue] = {
            DOC: {"pk": 4, "valid_part_types": [{"pk": 7}]},
            PARTS: self.collection(path),
        }
        for row in self.rows:
            assert isinstance(row, dict)
            details[PARTS + str(row["pk"]) + "/"] = row
        details.update(self.details)
        if route in details:
            return 200, details[route]
        return 404, {"detail": "Not found"}

    def mutate(self, method: str, route: str, body: JsonValue) -> tuple[int, JsonValue]:
        if method + " " + route in self.failures:
            return self.failures[method + " " + route], {"detail": "Denied"}
        if route in {PAGE + "rotate/", PAGE + "crop/"} and method == "POST":
            row = self.rows[0]
            assert isinstance(row, dict)
            row["image"] = {"uri": "/media/modified.png", "size": [80, 100]}
            if route in self.failures:
                return self.failures[route], {"detail": "Later geometry save failed"}
            return 200, {"status": "done"}
        if route == DOC + "bulk_move_parts/" and method == "POST":
            assert isinstance(body, dict)
            ids, index = body["parts"], body["index"]
            assert isinstance(ids, list)
            assert isinstance(index, int)
            selected: list[JsonValue] = []
            slots: list[JsonValue] = []
            for row in self.rows:
                assert isinstance(row, dict)
                if row["pk"] in ids:
                    selected.append(row)
                    slots.append(None)
                else:
                    slots.append(row)
            position = len(slots) if index == -1 else index
            moved = slots[:position] + selected + slots[position:]
            self.rows[:] = [row for row in moved if row is not None]
            for order, row in enumerate(self.rows):
                assert isinstance(row, dict)
                row["order"] = order
            return self.failures.get(route, 200), {"status": "moved"}
        if route == PAGE and method == "PATCH":
            row = self.rows[0]
            assert isinstance(row, dict)
            if body is not None:
                assert isinstance(body, dict)
                row.update(body)
            return 200, row
        return 405, {"detail": "Unexpected write"}


@contextmanager
def page_fixture(
    *, paginated: bool = False, prefix: str = ""
) -> Generator[PageFixture]:
    fixture = PageFixture("", paginated, prefix)

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            multipart = self.headers.get("Content-Type", "").startswith("multipart/")
            if multipart:
                fixture.uploads.append(raw)
            body = (
                TypeAdapter[JsonValue](JsonValue).validate_json(raw)
                if raw and not multipart
                else None
            )
            status, result = fixture.respond(self.command, self.path, body)
            payload = TypeAdapter[JsonValue](JsonValue).dump_json(result)
            self.send_response(status)
            if status == 302:
                route = urlsplit(self.path).path.removeprefix(prefix)
                self.send_header(
                    "Location", fixture.locations.get(route, prefix + PAGE)
                )
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

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = PageFixture(
            f"http://127.0.0.1:{server.server_port}{prefix}/", paginated, prefix
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def page_session(fixture: PageFixture) -> AsyncGenerator[ClientSession]:
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
