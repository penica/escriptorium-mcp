"""Bulk line mutations preserve scope, native payloads and failure semantics."""

import anyio
import pytest
from mcp_types import TextContent
from pydantic import JsonValue

from tests.segmentation_fixture import (
    BASELINE,
    LINES,
    POLYGON,
    SegmentationFixture,
    segmentation_fixture,
    segmentation_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("paginated", [False, True])
def test_bulk_create_injects_page_and_preserves_nested_text(*, paginated: bool) -> None:
    # Given a local region, document type and layer on a later inventory page.
    line: dict[str, JsonValue] = {
        "baseline": None,
        "mask": POLYGON,
        "region": 22,
        "typology": 7,
        "external_id": "č-line",
        "order": 0,
        "transcriptions": [
            {"transcription": 3, "content": "č", "graphs": None, "avg_confidence": 0.0}
        ],
    }

    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When native bulk creation is requested.
            result = await invoke(
                session,
                "bulk_create_lines",
                {"document_id": 4, "page_id": 10, "lines": [line]},
            )
            # Then the created line detail retains its nested text.
            assert result == {
                "status": "ok",
                "lines": [{**line, "document_part": 10, "pk": 13}],
            }

    with segmentation_fixture(paginated=paginated) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        LINES + "bulk_create/",
        {"lines": [{**line, "document_part": 10}]},
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"pk": 11, "external_id": None, "order": 0},
        {"pk": 12, "baseline": None},
        {"pk": 11, "mask": None},
        {"pk": 11, "region": None, "typology": None},
        {"pk": 11, "region": 22, "typology": 7, "baseline": BASELINE},
    ],
)
def test_bulk_update_preserves_omitted_nullable_and_zero_fields(
    patch: dict[str, JsonValue],
) -> None:
    # Given scoped geometry with both a baseline and a mask.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When applying a partial native update.
            result = await invoke(
                session,
                "bulk_update_lines",
                {"document_id": 4, "page_id": 10, "lines": [patch]},
            )
            # Then only supplied fields change and detail remains present.
            assert isinstance(result, dict)
            rows = result["lines"]
            assert isinstance(rows, list)
            row = rows[0]
            assert isinstance(row, dict)
            assert all(row[key] == value for key, value in patch.items())
            assert row["transcriptions"]

    with segmentation_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("PUT", LINES + "bulk_update/", {"lines": [patch]})


def test_bulk_delete_removes_line_and_nested_text() -> None:
    # Given geometry with attached transcriptions and history.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            old_rows = list(fixture.records)
            # When actual line deletion is requested.
            result = await invoke(
                session,
                "bulk_delete_lines",
                {"document_id": 4, "page_id": 10, "line_ids": [11, 12]},
            )
            # Then rows disappear and deleted detailed records are returned.
            assert result == {"status": "ok", "lines": old_rows}
            assert fixture.records == []

    with segmentation_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", LINES + "bulk_delete/", {"lines": [11, 12]})


def test_failed_bulk_update_exposes_partial_write_without_retry() -> None:
    # Given a server saving the first row before a later save fails.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When the batch is submitted once.
            result = await session.call_tool(
                "bulk_update_lines",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": [{"pk": 11, "order": 3}, {"pk": 12, "order": 4}],
                },
            )
            # Then failure is explicit and partial application is warned about.
            assert result.is_error
            block = result.content[0]
            assert isinstance(block, TextContent)
            assert "partial" in block.text.lower()

    with segmentation_fixture() as fixture:
        fixture.failures[LINES + "bulk_update/"] = 500
        anyio.run(run, fixture)
    first, second = fixture.records
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    assert first["order"] == 3
    assert second["order"] == 1
    assert sum(method == "PUT" for method, _path, _body in fixture.requests) == 1


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("bulk_create_lines", {"lines": [{"baseline": BASELINE, "region": 99}]}),
        ("bulk_create_lines", {"lines": [{"baseline": BASELINE, "typology": 99}]}),
        (
            "bulk_create_lines",
            {
                "lines": [
                    {
                        "baseline": BASELINE,
                        "transcriptions": [{"transcription": 99, "content": "x"}],
                    }
                ]
            },
        ),
        ("bulk_update_lines", {"lines": [{"pk": 99, "order": 0}]}),
        ("bulk_update_lines", {"lines": [{"pk": 11, "region": 99}]}),
        ("bulk_update_lines", {"lines": [{"pk": 11, "typology": 99}]}),
        ("bulk_update_lines", {"lines": [{"pk": 11, "baseline": None, "mask": None}]}),
        ("bulk_delete_lines", {"line_ids": [11, 99]}),
        ("merge_lines", {"line_ids": [11, 99]}),
        ("regenerate_line_masks", {"line_ids": [11, 99]}),
    ],
)
def test_foreign_references_prevent_every_write(
    tool: str, arguments: dict[str, JsonValue]
) -> None:
    # Given a mixed selection or globally valid but foreign reference.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When trying to mutate through the selected page.
            result = await session.call_tool(
                tool, {"document_id": 4, "page_id": 10, **arguments}
            )
            # Then no partial subset is silently accepted.
            assert result.is_error

    with segmentation_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _path, _body in fixture.requests)


def test_merge_rejects_mask_only_line_before_write() -> None:
    # Given a valid legacy mask-only line without a baseline.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When merging it with a baseline line.
            result = await session.call_tool(
                "merge_lines", {"document_id": 4, "page_id": 10, "line_ids": [11, 12]}
            )
            # Then unsupported merge geometry is rejected before deletion.
            assert result.is_error

    with segmentation_fixture() as fixture:
        row = fixture.records[1]
        assert isinstance(row, dict)
        row["baseline"] = None
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _path, _body in fixture.requests)
