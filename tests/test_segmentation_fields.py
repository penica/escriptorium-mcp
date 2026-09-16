"""Single-element editable fields and explicit region-lock feature detection."""

import anyio
import pytest
from pydantic import JsonValue

from tests.segmentation_fixture import (
    BLOCKS,
    LINES,
    POLYGON,
    SegmentationFixture,
    segmentation_fixture,
    segmentation_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("locked", [False, True])
def test_region_lock_patch_checks_metadata_and_preserves_false(*, locked: bool) -> None:
    # Given writable locking advertised by the installed backend.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When setting or clearing a region editor lock.
            result = await invoke(
                session,
                "update_region",
                {
                    "target": {"document_id": 4, "page_id": 10, "element_id": 21},
                    "changes": {"locked": locked, "external_id": ""},
                },
            )
            # Then the exact boolean and blank external ID survive.
            assert isinstance(result, dict)
            assert result["locked"] is locked
            assert result["external_id"] == ""

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert ("OPTIONS", BLOCKS + "21/", None) in fixture.requests
    assert fixture.requests[-1] == (
        "PATCH",
        BLOCKS + "21/",
        {"locked": locked, "external_id": ""},
    )


def test_create_locked_region_checks_collection_metadata() -> None:
    # Given a supported block type and advertised writable lock field.
    region: dict[str, JsonValue] = {
        "document_part": 10,
        "box": POLYGON,
        "locked": True,
        "typology": 8,
    }

    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When creating a locked region.
            result = await invoke(
                session, "create_region", {"document_id": 4, "region": region}
            )
            # Then the submitted fields reach the native creation endpoint.
            assert result == {**region, "pk": 30}

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert ("OPTIONS", BLOCKS, None) in fixture.requests
    assert fixture.requests[-1] == ("POST", BLOCKS, region)


@pytest.mark.parametrize("status", [200, 403])
def test_unavailable_locking_or_denied_metadata_prevents_patch(status: int) -> None:
    # Given absent locked metadata or a permission-denied OPTIONS response.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When requesting a lock mutation.
            result = await session.call_tool(
                "update_region",
                {
                    "target": {"document_id": 4, "page_id": 10, "element_id": 21},
                    "changes": {"locked": True},
                },
            )
            # Then the lock is never silently ignored or written after denial.
            assert result.is_error

    with segmentation_fixture() as fixture:
        fixture.metadata.clear()
        fixture.metadata["actions"] = {"PUT": {"box": {"type": "field"}}}
        fixture.failures["OPTIONS " + BLOCKS + "21/"] = status
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("OPTIONS", BLOCKS + "21/", None)
    assert all(
        method in {"GET", "OPTIONS"} for method, _path, _body in fixture.requests
    )


def test_mask_only_single_creation_retains_external_id_and_zero_order() -> None:
    # Given a mask-only legacy line with an explicit nullable baseline.
    line: dict[str, JsonValue] = {
        "document_part": 10,
        "baseline": None,
        "mask": POLYGON,
        "external_id": None,
        "order": 0,
    }

    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When creating it through the existing single-line tool.
            result = await invoke(
                session, "create_line", {"document_id": 4, "line": line}
            )
            # Then the new writable fields are included unchanged.
            assert result == {**line, "pk": 30}

    with segmentation_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", LINES, line)


@pytest.mark.parametrize(
    "changes", [{"baseline": None, "mask": None}, {"baseline": None}]
)
def test_single_geometry_patch_checks_final_stored_shape(
    changes: dict[str, JsonValue],
) -> None:
    # Given a baseline-only existing line.
    async def run(fixture: SegmentationFixture) -> None:
        async with segmentation_session(fixture) as session:
            # When removing its final remaining geometry.
            result = await session.call_tool(
                "update_line",
                {
                    "target": {"document_id": 4, "page_id": 10, "element_id": 11},
                    "changes": changes,
                },
            )
            # Then the invalid final state is rejected before mutation.
            assert result.is_error

    with segmentation_fixture() as fixture:
        row = fixture.records[0]
        assert isinstance(row, dict)
        row["mask"] = None
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _path, _body in fixture.requests)
