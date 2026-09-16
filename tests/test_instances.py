import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter
from typing_extensions import override

from tests.mutation_fixture import Case, api_fixture, exercise


@pytest.mark.parametrize(
    "case",
    [
        Case(
            "create_image_annotation",
            {
                "document_id": 7,
                "page_id": 9,
                "data": {
                    "taxonomy": 3,
                    "coordinates": [[10, 20], [100, 200]],
                },
            },
            "documents/7/parts/9/annotations/image/",
            payload={
                "part": 9,
                "taxonomy": 3,
                "coordinates": [[10, 20], [100, 200]],
                "components": [],
            },
        ),
        Case(
            "update_image_annotation",
            {
                "target": {"document_id": 7, "page_id": 9, "annotation_id": 5},
                "changes": {"comments": ["Corrected"]},
            },
            "documents/7/parts/9/annotations/image/5/",
            "PATCH",
            {"comments": ["Corrected"], "components": []},
        ),
        Case(
            "create_text_annotation",
            {
                "document_id": 7,
                "page_id": 9,
                "data": {
                    "taxonomy": 4,
                    "transcription": 6,
                    "start_line": 11,
                    "end_line": 11,
                    "start_offset": 0,
                    "end_offset": 5,
                    "components": [{"component": 3, "value": "Name"}],
                },
            },
            "documents/7/parts/9/annotations/text/",
            payload={
                "part": 9,
                "taxonomy": 4,
                "transcription": 6,
                "start_line": 11,
                "end_line": 11,
                "start_offset": 0,
                "end_offset": 5,
                "components": [{"component": 3, "value": "Name"}],
            },
        ),
        Case(
            "update_text_annotation",
            {
                "target": {"document_id": 7, "page_id": 9, "annotation_id": 5},
                "changes": {
                    "taxonomy": 8,
                    "components": [{"component": 3, "value": None}],
                },
            },
            "documents/7/parts/9/annotations/text/5/",
            "PATCH",
            {"taxonomy": 8, "components": [{"component": 3, "value": None}]},
        ),
        Case(
            "delete_annotation",
            {
                "kind": "image",
                "target": {"document_id": 7, "page_id": 9, "annotation_id": 5},
            },
            "documents/7/parts/9/annotations/image/5/",
            "DELETE",
        ),
    ],
)
def test_annotation_mutations_send_exact_api_contract(case: Case) -> None:
    with api_fixture() as fixture:
        anyio.run(exercise, fixture, case)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"taxonomy": None},
        {"start_offset": -1},
        {"end_offset": 2147483648},
        {
            "components": [
                {"component": 3, "value": "one"},
                {"component": 3, "value": "two"},
            ]
        },
        {"part": 99},
        {"components": [{"component": 3, "value": ""}]},
    ],
)
def test_invalid_annotation_changes_do_not_reach_api(
    changes: dict[str, JsonValue],
) -> None:
    case = Case(
        "update_text_annotation",
        {
            "target": {"document_id": 7, "page_id": 9, "annotation_id": 5},
            "changes": changes,
        },
    )
    with api_fixture() as fixture:
        anyio.run(exercise, fixture, case)


def test_annotation_reads_preserve_w3c_and_filter_query() -> None:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            body = (
                b'{"count":1,"next":null,"results":[{"pk":5}]}'
                if "?" in self.path
                else b'{"pk":5,"as_w3c":{"type":"Annotation"}}'
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            _ = self.wfile.write(body)

        @override
        def log_message(self, format: str, *args: str) -> None:
            return

    async def exercise_reads(port: int) -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "escriptorium_mcp.server"],
            env={
                "ESCRIPTORIUM_URL": f"http://127.0.0.1:{port}/",
                "ESCRIPTORIUM_API_KEY": "fixture-key",
            },
        )
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            _ = await session.initialize()
            listing = await session.call_tool(
                "list_annotations",
                {
                    "document_id": 7,
                    "page_id": 9,
                    "kind": "text",
                    "transcription_id": 6,
                },
            )
            assert not listing.is_error, listing.content
            assert isinstance(listing.content[0], TextContent)
            assert TypeAdapter(JsonValue).validate_json(listing.content[0].text) == {
                "count": 1,
                "next": None,
                "results": [{"pk": 5}],
            }
            result = await session.call_tool(
                "get_annotation",
                {
                    "target": {"document_id": 7, "page_id": 9, "annotation_id": 5},
                    "kind": "image",
                },
            )
            assert not result.is_error, result.content
            assert isinstance(result.content[0], TextContent)
            assert TypeAdapter(JsonValue).validate_json(result.content[0].text) == {
                "pk": 5,
                "as_w3c": {"type": "Annotation"},
            }
            invalid = await session.call_tool(
                "list_annotations",
                {
                    "document_id": 7,
                    "page_id": 9,
                    "kind": "image",
                    "transcription_id": 6,
                },
            )
            assert invalid.is_error

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            anyio.run(exercise_reads, server.server_port)
        finally:
            server.shutdown()
            thread.join()
    assert requests == [
        "/api/documents/7/parts/9/annotations/text/?transcription=6",
        "/api/documents/7/parts/9/annotations/image/5/",
    ]


@pytest.mark.parametrize("kind", ["image", "text"])
def test_null_comments_clear_annotations(kind: str) -> None:
    case = Case(
        f"update_{kind}_annotation",
        {
            "target": {"document_id": 7, "page_id": 9, "annotation_id": 5},
            "changes": {"comments": None},
        },
        f"documents/7/parts/9/annotations/{kind}/5/",
        "PATCH",
        {"comments": None, "components": []},
    )
    with api_fixture() as fixture:
        anyio.run(exercise, fixture, case)
