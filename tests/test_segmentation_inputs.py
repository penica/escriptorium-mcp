"""Public segmentation boundaries reject malformed batches before upstream calls."""

from typing import Final

import anyio
import pytest
from pydantic import JsonValue

from tests.segmentation_fixture import (
    BASELINE,
    SegmentationFixture,
    segmentation_fixture,
    segmentation_session,
)

INVALID_INPUTS: Final[list[tuple[str, dict[str, JsonValue]]]] = [
    ("bulk_create_lines", {"lines": []}),
    ("bulk_create_lines", {"lines": [{}]}),
    ("bulk_create_lines", {"lines": [{"baseline": None, "mask": None}]}),
    ("bulk_create_lines", {"lines": [{"baseline": [[0, 0]]}]}),
    ("bulk_create_lines", {"lines": [{"mask": [[0, 0], [1, 1]]}]}),
    ("bulk_create_lines", {"lines": [{"baseline": [[0, 0, 0], [1, 1]]}]}),
    ("bulk_create_lines", {"lines": [{"baseline": BASELINE, "pk": 55}]}),
    ("bulk_create_lines", {"lines": [{"baseline": BASELINE, "document_part": 99}]}),
    (
        "bulk_create_lines",
        {"lines": [{"baseline": BASELINE, "external_id": "x" * 129}]},
    ),
    ("bulk_create_lines", {"lines": [{"baseline": BASELINE, "order": -1}]}),
    ("bulk_create_lines", {"lines": [{"baseline": BASELINE, "order": None}]}),
    (
        "bulk_create_lines",
        {
            "lines": [
                {
                    "baseline": BASELINE,
                    "transcriptions": [{"transcription": 2, "line": 11}],
                }
            ]
        },
    ),
    ("bulk_update_lines", {"lines": []}),
    ("bulk_update_lines", {"lines": [{"pk": 11}]}),
    ("bulk_update_lines", {"lines": [{"pk": 11, "order": 0}, {"pk": 11, "order": 0}]}),
    ("bulk_update_lines", {"lines": [{"pk": 11, "document_part": 99}]}),
    ("bulk_delete_lines", {"line_ids": []}),
    ("bulk_delete_lines", {"line_ids": [11, 11]}),
    ("merge_lines", {"line_ids": [11]}),
    ("merge_lines", {"line_ids": [11, 11]}),
    ("merge_lines", {"line_ids": list(range(1, 10))}),
    ("regenerate_line_masks", {"line_ids": []}),
    ("regenerate_line_masks", {"line_ids": [11, 11]}),
]


@pytest.mark.parametrize(("tool", "arguments"), INVALID_INPUTS)
def test_invalid_input_fails_before_network(
    tool: str, arguments: dict[str, JsonValue]
) -> None:
    # Given structurally invalid, empty, duplicate or caller-controlled identities.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When the public schema parses the input.
            result = await session.call_tool(
                tool, {"document_id": 4, "page_id": 10, **arguments}
            )
            # Then invalid input cannot touch upstream state.
            assert result.is_error

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize(
    "tool",
    [
        "bulk_delete_lines",
        "merge_lines",
        "regenerate_line_masks",
        "recalculate_line_order",
    ],
)
def test_foreign_parent_page_prevents_mutation(tool: str) -> None:
    # Given an inaccessible page under the requested document.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            arguments: dict[str, JsonValue] = {"document_id": 4, "page_id": 99}
            if tool != "recalculate_line_order":
                arguments["line_ids"] = [11, 12]
            # When a mutation targets that page.
            result = await session.call_tool(tool, arguments)
            # Then parent membership is checked before any write.
            assert result.is_error

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", "/api/documents/4/parts/99/", None)]
