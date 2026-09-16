from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.download_fixture import (
    COLLECTION,
    FP,
    OTHER_FP,
    DownloadFixture,
    download_fixture,
    download_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def _record(
    fixture: DownloadFixture, fingerprint: str, task_report_id: int | None
) -> dict[str, JsonValue]:
    return dict(fixture.detail, fingerprint=fingerprint, task_report_id=task_report_id)


def test_downloads_without_page_selection_keep_full_legacy_collection() -> None:
    # Given two native download pages with a row only on the second page.
    with download_fixture() as fixture:
        first = _record(fixture, FP, None)
        second = _record(fixture, OTHER_FP, 7)
        fixture.responses[COLLECTION] = {
            "count": 2,
            "next": "?page=2",
            "results": [first],
            "future": {"retained": True},
        }
        fixture.responses[COLLECTION + "?page=2"] = {
            "count": 2,
            "next": None,
            "results": [second],
        }

        async def run() -> None:
            # When the established unbounded call omits pagination.
            async with download_session(fixture) as session:
                result = await invoke(session, "list_downloads", {})
            # Then it retains the original complete flattened collection response.
            assert result == {
                "count": 2,
                "next": None,
                "results": [first, second],
                "future": {"retained": True},
            }

        anyio.run(run)
    assert fixture.requests == [
        ("GET", COLLECTION),
        ("GET", COLLECTION + "?page=2"),
    ]


@pytest.mark.parametrize(
    ("page", "response", "expected_pages"),
    [
        (
            1,
            {"count": 2, "next": "?page=2&paginate_by=1", "previous": None},
            (2, None),
        ),
        (
            2,
            {
                "count": 2,
                "next": None,
                "previous": "?page=1&paginate_by=1",
            },
            (None, 1),
        ),
        (
            3,
            {
                "count": 2,
                "next": None,
                "previous": "?page=2&paginate_by=1",
            },
            (None, 2),
        ),
    ],
)
def test_download_page_selection_fetches_exactly_one_native_page(
    page: int,
    response: dict[str, JsonValue],
    expected_pages: tuple[int | None, int | None],
) -> None:
    # Given first, final and empty native pages with distinct continuation states.
    with download_fixture() as fixture:
        requested = COLLECTION + f"?page={page}&paginate_by=1"
        row = _record(fixture, FP if page == 1 else OTHER_FP, page)
        fixture.responses[requested] = {
            **response,
            "results": [row] if page < 3 else [],
            "future": {"page": page},
        }

        async def run() -> None:
            # When an actual MCP client requests one bounded native page.
            async with download_session(fixture) as session:
                result = await invoke(
                    session,
                    "list_downloads",
                    {"pagination": {"page": page, "page_size": 1}},
                )
            # Then the upstream envelope and guarded page metadata describe one page.
            assert isinstance(result, dict)
            assert result["results"] == ([row] if page < 3 else [])
            assert result["future"] == {"page": page}
            assert result["pagination"] == {
                "mode": "native_page",
                "page": page,
                "page_size": 1,
                "returned_count": 1 if page < 3 else 0,
                "native_total": 2,
                "native_total_scope": "collection",
                "filtered_total": None,
                "filtered_total_scope": "not_filtered",
                "has_next": expected_pages[0] is not None,
                "has_previous": expected_pages[1] is not None,
                "next_page": expected_pages[0],
                "previous_page": expected_pages[1],
                "collection_consistency": "snapshot_not_guaranteed",
            }

        anyio.run(run)
    assert fixture.requests == [("GET", requested)]


def test_download_page_filter_reports_only_source_page_filtered_count() -> None:
    # Given a page containing one matching report and one unrelated report.
    with download_fixture() as fixture:
        requested = COLLECTION + "?page=2&paginate_by=2"
        matched = _record(fixture, FP, 7)
        unrelated = _record(fixture, OTHER_FP, 8)
        fixture.responses[requested] = {
            "count": 9,
            "next": "?page=3&paginate_by=2",
            "previous": "?page=1&paginate_by=2",
            "results": [matched, unrelated],
        }

        async def run() -> None:
            # When the local task-report filter is applied to a selected native page.
            async with download_session(fixture) as session:
                result = await invoke(
                    session,
                    "list_downloads",
                    {
                        "task_report_id": 7,
                        "pagination": {"page": 2, "page_size": 2},
                    },
                )
            # Then it never claims to know the whole collection's filtered total.
            assert isinstance(result, dict)
            assert result["count"] is None
            assert result["results"] == [matched]
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["native_total"] == 9
            assert metadata["filtered_total"] == 1
            assert metadata["filtered_total_scope"] == "source_page"

        anyio.run(run)
    assert fixture.requests == [("GET", requested)]


@pytest.mark.parametrize(
    "pagination",
    [{"page": 0}, {"page": True}, {"page_size": 0}, {"page_size": 51}],
)
def test_download_page_selection_rejects_invalid_bounds_before_http(
    pagination: dict[str, JsonValue],
) -> None:
    # Given malformed public pagination input.
    with download_fixture() as fixture:

        async def run() -> None:
            # When it crosses the actual MCP validation boundary.
            async with download_session(fixture) as session:
                response = await session.call_tool(
                    "list_downloads", {"pagination": pagination}
                )
            # Then no authenticated download request is made.
            assert response.is_error

        anyio.run(run)
    assert fixture.requests == []


@pytest.mark.parametrize("next_link", ["?page=bad", "/api/tasks/?page=2"])
def test_download_page_selection_rejects_malformed_or_cross_route_links(
    next_link: str,
) -> None:
    # Given a one-page response with a continuation unsafe to advertise.
    with download_fixture() as fixture:
        requested = COLLECTION + "?page=1"
        fixture.responses[requested] = {
            "count": 2,
            "next": next_link,
            "previous": None,
            "results": [_record(fixture, FP, None)],
        }

        async def run() -> None:
            # When the MCP receives the malformed native continuation.
            async with download_session(fixture) as session:
                response = await session.call_tool(
                    "list_downloads", {"pagination": {"page": 1}}
                )
            # Then it rejects the response without following the supplied link.
            assert response.is_error

        anyio.run(run)
    assert fixture.requests == [("GET", requested)]
