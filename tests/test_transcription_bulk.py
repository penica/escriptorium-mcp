"""Bulk transcription contracts through the real STDIO and worker processes."""

import anyio
import pytest
from mcp_types import TextContent
from pydantic import JsonValue

from tests.transcription_fixture import (
    TEXTS,
    TranscriptionFixture,
    invoke,
    transcription_fixture,
    transcription_session,
)


@pytest.mark.parametrize("paginated", [False, True])
def test_create_uses_scoped_post_and_preserves_normalized_response(
    *, paginated: bool
) -> None:
    # Given local page lines and a document-owned layer, including later list pages.
    lines: list[JsonValue] = [{"line": 12, "transcription": 3, "content": "<b>č</b>"}]

    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When submitted through STDIO.
            result = await invoke(
                session,
                "bulk_create_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": lines,
                },
            )
            # Then the actual normalized server result is preserved.
            assert result == {
                "status": "ok",
                "lines": [{"pk": 93, "content": "normalized"}],
            }

    with transcription_fixture(paginated=paginated) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", TEXTS + "bulk_create/", {"lines": lines})


@pytest.mark.parametrize(
    "patch",
    [
        {"pk": 91, "content": ""},
        {"pk": 91, "graphs": None, "avg_confidence": None},
        {
            "pk": 91,
            "graphs": [
                {},
                {"c": "č"},
                {"confidence": 0.0},
                {"poly": [[-1, 0], [2, 0], [2, 3]]},
            ],
            "avg_confidence": 2.0,
        },
        {"pk": 91, "transcription": 3, "line": 12},
    ],
)
def test_update_uses_put_and_preserves_explicit_fields(
    patch: dict[str, JsonValue],
) -> None:
    # Given a scoped row and patch preserving the distinction between omitted and null.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When the patch is submitted.
            result = await invoke(
                session,
                "bulk_update_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": [patch],
                },
            )
            # Then its actual stored response is returned.
            assert isinstance(result, list)
            row = result[0]
            assert isinstance(row, dict)
            assert all(row[key] == value for key, value in patch.items())

    with transcription_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("PUT", TEXTS + "bulk_update/", {"lines": [patch]})


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        (
            "bulk_create_line_transcriptions",
            {"lines": [{"line": 99, "transcription": 3, "content": "x"}]},
        ),
        (
            "bulk_create_line_transcriptions",
            {"lines": [{"line": 11, "transcription": 99, "content": "x"}]},
        ),
        (
            "bulk_create_line_transcriptions",
            {"lines": [{"line": 11, "transcription": 3, "content": "x"}] * 2},
        ),
        ("bulk_update_line_transcriptions", {"lines": [{"pk": 99, "content": "x"}]}),
        ("bulk_update_line_transcriptions", {"lines": [{"pk": 91, "line": 99}]}),
        (
            "bulk_update_line_transcriptions",
            {"lines": [{"pk": 91, "transcription": 99}]},
        ),
        (
            "bulk_update_line_transcriptions",
            {"lines": [{"pk": 91, "content": "x"}] * 2},
        ),
        ("bulk_update_line_transcriptions", {"lines": [{"pk": 91, "line": 12}]}),
        ("bulk_clear_line_transcriptions", {"line_transcription_ids": [99]}),
        ("bulk_clear_line_transcriptions", {"line_transcription_ids": [91, 91]}),
    ],
)
def test_invalid_scope_or_duplicates_prevent_every_write(
    tool: str, arguments: dict[str, JsonValue]
) -> None:
    # Given foreign IDs or conflicting row identities on a legacy global-lookup API.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When the unsafe batch is requested.
            result = await session.call_tool(
                tool, {"document_id": 4, "page_id": 10, **arguments}
            )
            # Then it is rejected before the fixture can receive a write.
            assert result.is_error

    with transcription_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _path, _body in fixture.requests)


@pytest.mark.parametrize(
    "patch",
    [
        {"pk": 91},
        {"pk": 91, "content": None},
        {"pk": 91, "graphs": [{"c": None}]},
        {"pk": 91, "graphs": [{"c": "ab"}]},
        {"pk": 91, "graphs": [{"poly": [[0, 0], [1, 1]]}]},
        {"pk": 91, "graphs": [{"poly": [[0, 0, 0], [1, 1], [2, 2]]}]},
        {"pk": 91, "graphs": [{"confidence": 1.1}]},
    ],
)
def test_invalid_graphs_and_empty_patches_fail_before_network(
    patch: dict[str, JsonValue],
) -> None:
    # Given invalid fields at the public MCP boundary.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When validation parses the payload.
            result = await session.call_tool(
                "bulk_update_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": [patch],
                },
            )
            # Then validation rejects it without upstream access.
            assert result.is_error

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


def test_failed_nonatomic_update_reports_partial_application_without_retry() -> None:
    # Given a server that saves the first row and rejects a later row.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When one native batch is submitted.
            result = await session.call_tool(
                "bulk_update_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": [
                        {"pk": 91, "content": "saved"},
                        {"pk": 92, "content": "rejected"},
                    ],
                },
            )
            # Then callers are warned about partial application.
            assert result.is_error
            block = result.content[0]
            assert isinstance(block, TextContent)
            assert "partial" in block.text.lower()

    with transcription_fixture() as fixture:
        fixture.failures[TEXTS + "bulk_update/"] = 400
        anyio.run(run, fixture)
    assert sum(method == "PUT" for method, _path, _body in fixture.requests) == 1
    assert isinstance(fixture.records[0], dict)
    assert fixture.records[0]["content"] == "saved"
    assert isinstance(fixture.records[1], dict)
    assert fixture.records[1]["content"] == "č"


def test_bulk_clear_blanks_content_without_deleting_rows_or_history() -> None:
    # Given stored text with graph metadata and history.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When clearing through the native 204 POST endpoint.
            result = await session.call_tool(
                "bulk_clear_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "line_transcription_ids": [91, 92],
                },
            )
            # Then the empty successful HTTP response remains a successful MCP call.
            assert not result.is_error, result.content

    with transcription_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", TEXTS + "bulk_delete/", {"lines": [91, 92]})
    assert all(method != "DELETE" for method, _path, _body in fixture.requests)
    assert len(fixture.records) == 2
    row = fixture.records[0]
    assert isinstance(row, dict)
    assert row["content"] == ""
    assert row["graphs"] == []
    assert row["avg_confidence"] == 0.0
    assert row["versions"] == [{"content": "history"}]


def test_foreign_page_prevents_any_batch_write() -> None:
    # Given a page hidden from the requested document.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When attempting to clear a known text ID through the wrong page.
            result = await session.call_tool(
                "bulk_clear_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 99,
                    "line_transcription_ids": [91],
                },
            )
            # Then the page membership check prevents all mutations.
            assert result.is_error

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", "/api/documents/4/parts/99/", None)]


def test_multiple_updated_rows_remain_a_complete_result_array() -> None:
    # Given two independently addressable records in one page.
    lines: list[JsonValue] = [
        {"pk": 91, "content": "first"},
        {"pk": 92, "content": "second"},
    ]

    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When both records are updated in one native PUT.
            result = await invoke(
                session,
                "bulk_update_line_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": lines,
                },
            )
            # Then all results retain their array shape and input order.
            assert isinstance(result, list)
            assert result == fixture.records
            assert len(result) == 2

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("PUT", TEXTS + "bulk_update/", {"lines": lines})
