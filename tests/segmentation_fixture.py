"""Source-shaped segmentation HTTP fixture with observable stored mutations."""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

DOC: Final = "/api/documents/4/"
PAGE: Final = DOC + "parts/10/"
LINES: Final = PAGE + "lines/"
BLOCKS: Final = PAGE + "blocks/"
BASELINE: Final[JsonValue] = [[0, 1], [4, 1]]
POLYGON: Final[JsonValue] = [[0, 0], [4, 0], [4, 2]]


@dataclass(frozen=True, slots=True)
class SegmentationFixture:
    """Accumulate requests and stored rows for mutation assertions."""

    url: str
    paginated: bool = False
    requests: list[tuple[str, str, JsonValue]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, JsonValue] = field(
        default_factory=lambda: {
            "actions": {
                verb: {"locked": {"type": "boolean"}}
                for verb in ("POST", "PUT", "PATCH")
            }
        }
    )
    records: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "pk": number,
                "document_part": 10,
                "baseline": BASELINE,
                "mask": POLYGON,
                "region": 21,
                "typology": 7,
                "order": number - 11,
                "transcriptions": [
                    {
                        "pk": number + 80,
                        "line": number,
                        "transcription": 2,
                        "content": f"text-{number}",
                        "graphs": [],
                        "versions": ["old"],
                    }
                ],
            }
            for number in (11, 12)
        ]
    )
    regions: list[JsonValue] = field(
        default_factory=lambda: [
            {
                "pk": number,
                "document_part": 10,
                "box": POLYGON,
                "typology": 8,
                "locked": False,
            }
            for number in (21, 22)
        ]
    )

    def collection(self, path: str, rows: list[JsonValue]) -> JsonValue:
        if not self.paginated:
            return rows
        second = parse_qs(urlsplit(path).query).get("page") == ["2"]
        return {
            "count": len(rows),
            "next": None
            if second
            else self.url.rstrip("/") + urlsplit(path).path + "?page=2",
            "results": rows[1:] if second else rows[:1],
        }

    def respond(self, method: str, path: str, body: JsonValue) -> tuple[int, JsonValue]:
        self.requests.append((method, path, body))
        route = urlsplit(path).path
        if route in self.failures and route != LINES + "bulk_update/":
            return self.failures[route], {"detail": "Fixture denied or unavailable"}
        if method == "OPTIONS":
            return self.failures.get("OPTIONS " + route, 200), self.metadata
        if method != "GET":
            return self.mutate(method, route, body)
        collections: dict[str, list[JsonValue]] = {
            LINES: self.records,
            BLOCKS: self.regions,
            DOC + "transcriptions/": [{"pk": 2}, {"pk": 3}],
        }
        if route in collections:
            return 200, self.collection(path, collections[route])
        details: dict[str, JsonValue] = {
            PAGE: {"pk": 10, "document": 4},
            DOC: {
                "pk": 4,
                "valid_line_types": [{"pk": 7}],
                "valid_block_types": [{"pk": 8}],
            },
        }
        for prefix, rows in ((LINES, self.records), (BLOCKS, self.regions)):
            for row in rows:
                assert isinstance(row, dict)
                details[prefix + str(row["pk"]) + "/"] = row
        if route in details:
            return 200, details[route]
        return 404, {"detail": "Unknown fixture route"}

    def mutate(self, method: str, route: str, body: JsonValue) -> tuple[int, JsonValue]:
        actions: dict[str, JsonValue] = {
            PAGE + "reset_masks/": {"status": "ok"},
            PAGE + "recalculate_ordering/": {
                "status": "done",
                "lines": [{"pk": 12, "order": 0}, {"pk": 11, "order": 1}],
            },
        }
        if route in actions and method == "POST":
            return 200, actions[route]
        if route == LINES + "bulk_create/" and method == "POST":
            assert isinstance(body, dict)
            entries = body["lines"]
            assert isinstance(entries, list)
            created: list[JsonValue] = []
            for number, entry in enumerate(entries, 13):
                assert isinstance(entry, dict)
                row: JsonValue = {**entry, "pk": number, "document_part": 10}
                self.records.append(row)
                created.append(row)
            return 200, {"status": "ok", "lines": created}
        if route == LINES + "bulk_update/" and method == "PUT":
            assert isinstance(body, dict)
            entries = body["lines"]
            assert isinstance(entries, list)
            changed: list[JsonValue] = []
            for entry in entries:
                assert isinstance(entry, dict)
                for row in self.records:
                    assert isinstance(row, dict)
                    if row["pk"] == entry["pk"]:
                        row.update(entry)
                        changed.append(row)
                if route in self.failures:
                    return self.failures[route], {"detail": "Later save failed"}
            return 200, {"status": "ok", "lines": changed}
        if route in {LINES + "bulk_delete/", LINES + "merge/"} and method == "POST":
            return self.delete_or_merge(route, body)
        return self.single_mutation(method, route, body)

    def delete_or_merge(self, route: str, body: JsonValue) -> tuple[int, JsonValue]:
        if route in {LINES + "bulk_delete/", LINES + "merge/"}:
            assert isinstance(body, dict)
            ids = body["lines"]
            assert isinstance(ids, list)
            deleted: list[JsonValue] = []
            for row in self.records[:]:
                assert isinstance(row, dict)
                if row["pk"] in ids:
                    deleted.append(row)
                    self.records.remove(row)
            if route == LINES + "merge/":
                merged: JsonValue = {
                    "pk": 13,
                    "document_part": 10,
                    "baseline": BASELINE,
                    "transcriptions": [
                        {"transcription": 2, "content": "geometry order"}
                    ],
                }
                self.records.append(merged)
                return 200, {
                    "status": "ok",
                    "lines": {"created": merged, "deleted": deleted},
                }
            return 200, {"status": "ok", "lines": deleted}
        return 405, {"detail": "Unexpected deletion route"}

    def single_mutation(
        self, method: str, route: str, body: JsonValue
    ) -> tuple[int, JsonValue]:
        for prefix, rows in ((LINES, self.records), (BLOCKS, self.regions)):
            if route == prefix and method == "POST":
                assert isinstance(body, dict)
                created_row: JsonValue = {**body, "pk": 30}
                rows.append(created_row)
                return 201, created_row
            for row in rows:
                assert isinstance(row, dict)
                if route == prefix + str(row["pk"]) + "/" and method == "PATCH":
                    assert isinstance(body, dict)
                    row.update(body)
                    return 200, row
        return 405, {"detail": "Unexpected mutation"}


@contextmanager
def segmentation_fixture(*, paginated: bool = False) -> Generator[SegmentationFixture]:
    fixture = SegmentationFixture("", paginated)

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            assert self.headers.get("Authorization") == "Token fixture-key"
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = TypeAdapter[JsonValue](JsonValue).validate_json(raw) if raw else None
            status, result = fixture.respond(self.command, self.path, body)
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

        def do_PUT(self) -> None:
            self.respond()

        def do_PATCH(self) -> None:
            self.respond()

        def do_OPTIONS(self) -> None:
            self.respond()

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        fixture = SegmentationFixture(
            f"http://127.0.0.1:{server.server_port}/", paginated
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            thread.join()


@asynccontextmanager
async def segmentation_session(
    fixture: SegmentationFixture,
) -> AsyncGenerator[ClientSession]:
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
