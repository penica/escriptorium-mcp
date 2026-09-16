"""Native segmentation actions through actual MCP subprocesses."""

from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from pydantic import JsonValue

from tests.segmentation_fixture import (
    BLOCKS,
    LINES,
    PAGE,
    SegmentationFixture,
    segmentation_fixture,
    segmentation_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    ("tool", "identity", "route"), [("get_line", 11, LINES), ("get_region", 21, BLOCKS)]
)
def test_detail_preserves_record(tool: str, identity: int, route: str) -> None:
    # Given detailed records with geometry and nested metadata.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When retrieving one element through STDIO.
            result = await invoke(
                session,
                tool,
                {"target": {"document_id": 4, "page_id": 10, "element_id": identity}},
            )
            # Then its full detail is retained.
            assert result == (
                fixture.records[0] if identity == 11 else fixture.regions[0]
            )

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("GET", route + str(identity) + "/", None)


def test_merge_returns_created_and_deleted_and_replaces_originals() -> None:
    # Given two page lines with nested text and history.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When merging in reversed input order.
            result = await invoke(
                session,
                "merge_lines",
                {"document_id": 4, "page_id": 10, "line_ids": [12, 11]},
            )
            # Then server geometry order and lossy metadata are passed through.
            assert isinstance(result, dict)
            lines = result["lines"]
            assert isinstance(lines, dict)
            assert lines["created"] == fixture.records[0]
            deleted = lines["deleted"]
            assert isinstance(deleted, list)
            assert len(deleted) == 2
            assert len(fixture.records) == 1

    with segmentation_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", LINES + "merge/", {"lines": [12, 11]})


@pytest.mark.parametrize("selection", [None, [12, 11]])
def test_mask_submission_preserves_queued_response(selection: list[int] | None) -> None:
    # Given all-page or explicitly selected eligible lines.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            args: dict[str, JsonValue] = {"document_id": 4, "page_id": 10}
            if selection is not None:
                args["line_ids"] = list(selection)
            # When mask regeneration is submitted.
            result = await invoke(session, "regenerate_line_masks", args)
            # Then acceptance is returned without invented completion or task IDs.
            assert result == {"status": "ok"}

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    method, route, body = fixture.requests[-1]
    assert method == "POST"
    assert route == PAGE + "reset_masks/" + ("?only=12%2C11" if selection else "")
    assert body is None


def test_recalculation_returns_whole_page_order_with_empty_body() -> None:
    # Given a page with an existing manual order.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When recalculation is requested.
            result = await invoke(
                session, "recalculate_line_order", {"document_id": 4, "page_id": 10}
            )
            # Then the native synchronous order result is retained.
            assert result == {
                "status": "done",
                "lines": [{"pk": 12, "order": 0}, {"pk": 11, "order": 1}],
            }

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", PAGE + "recalculate_ordering/", None)


@pytest.mark.parametrize("status", [400, 403, 404])
def test_mask_failure_is_returned_without_retry(status: int) -> None:
    # Given a quota, permission or unavailable-route response.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When submission fails upstream.
            response = await session.call_tool(
                "regenerate_line_masks", {"document_id": 4, "page_id": 10}
            )
            # Then it remains an MCP error.
            assert response.is_error

    with segmentation_fixture() as fixture:
        fixture.failures[PAGE + "reset_masks/"] = status
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _path, _body in fixture.requests) == 1
