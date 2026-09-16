"""Legacy nested endpoints cannot bypass explicit parent and record checks."""

from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from pydantic import JsonValue

from tests.segmentation_fixture import (
    BASELINE,
    BLOCKS,
    LINES,
    SegmentationFixture,
    segmentation_fixture,
    segmentation_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    "tool", ["get_line", "get_region", "bulk_delete_lines", "merge_lines"]
)
def test_legacy_foreign_record_is_rejected_despite_matching_pk(tool: str) -> None:
    # Given a legacy endpoint returning an element attached to another page.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            arguments: dict[str, JsonValue] = {
                "document_id": 4,
                "page_id": 10,
                "line_ids": [11, 12],
            }
            if tool in {"get_line", "get_region"}:
                arguments = {
                    "target": {
                        "document_id": 4,
                        "page_id": 10,
                        "element_id": 21 if tool == "get_region" else 11,
                    }
                }
            # When reading or selecting that returned identity.
            result = await session.call_tool(tool, arguments)
            # Then a matching PK cannot conceal foreign ownership.
            assert result.is_error

    with segmentation_fixture() as fixture:
        row = fixture.regions[0] if tool == "get_region" else fixture.records[0]
        assert isinstance(row, dict)
        row["document_part"] = 99
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _path, _body in fixture.requests)


def test_merge_accepts_eight_distinct_baseline_lines() -> None:
    # Given the maximum supported set of eight page-owned baselines.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When selecting exactly the backend maximum.
            result = await invoke(
                session,
                "merge_lines",
                {"document_id": 4, "page_id": 10, "line_ids": list(range(11, 19))},
            )
            # Then all eight originals are replaced by one server-created row.
            assert isinstance(result, dict)
            lines = result["lines"]
            assert isinstance(lines, dict)
            deleted = lines["deleted"]
            assert isinstance(deleted, list)
            assert len(deleted) == 8
            assert len(fixture.records) == 1

    with segmentation_fixture(paginated=True) as fixture:
        fixture.records.extend(
            {"pk": number, "document_part": 10, "baseline": BASELINE}
            for number in range(13, 19)
        )
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        LINES + "merge/",
        {"lines": list(range(11, 19))},
    )


def test_readonly_locked_metadata_prevents_write() -> None:
    # Given metadata advertising locked as read-only rather than writable.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When requesting an explicit unlock.
            result = await session.call_tool(
                "update_region",
                {
                    "target": {"document_id": 4, "page_id": 10, "element_id": 21},
                    "changes": {"locked": False},
                },
            )
            # Then capability presence alone does not authorize writing it.
            assert result.is_error

    with segmentation_fixture() as fixture:
        fixture.metadata["actions"] = {"PUT": {"locked": {"read_only": True}}}
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("OPTIONS", BLOCKS + "21/", None)
    assert all(
        method in {"GET", "OPTIONS"} for method, _path, _body in fixture.requests
    )


def test_bulk_create_checks_nested_duplicates_before_network() -> None:
    # Given duplicate text layers on one newly-created line.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When submitting conflicting nested text identities.
            response = await session.call_tool(
                "bulk_create_lines",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "lines": [
                        {
                            "baseline": BASELINE,
                            "transcriptions": [
                                {"transcription": 2, "content": "a"},
                                {"transcription": 2, "content": "b"},
                            ],
                        }
                    ],
                },
            )
            # Then creation is rejected before any lines could be written.
            assert response.is_error

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == []
