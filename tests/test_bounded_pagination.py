from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from escriptorium_mcp.bridge import call
from escriptorium_mcp.pagination import (
    PageSelection,
    annotate_filtered_page,
    paginated_request,
)
from tests.collection_fixture import collection_fixture

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_page_selection_is_strict_positive_and_bounded_by_native_maximum() -> None:
    assert PageSelection().page == 1
    assert PageSelection(page=2, page_size=50).page_size == 50
    for invalid in (
        {"page": 0},
        {"page": True},
        {"page_size": 0},
        {"page_size": 51},
        {"page_size": 2.0},
    ):
        with pytest.raises(ValidationError):
            _ = PageSelection.model_validate(invalid)


def test_request_helper_preserves_unbounded_behavior_and_guards_page_size() -> None:
    legacy = paginated_request("collections/", None, page_size_supported=False)
    assert legacy.paginate is True
    assert legacy.native_page is None
    assert legacy.query == {}

    bounded = paginated_request(
        "projects/",
        PageSelection(page=3, page_size=20),
        query={"name": "Register"},
        page_size_supported=True,
    )
    assert bounded.paginate is False
    assert bounded.native_page is True
    assert bounded.strict_pagination is True
    assert bounded.single_attempt is True
    assert bounded.query == {"name": "Register", "page": "3", "paginate_by": "20"}

    with pytest.raises(ToolError, match="does not support page_size"):
        _ = paginated_request(
            "collections/",
            PageSelection(page_size=2),
            page_size_supported=False,
        )


def test_one_native_page_preserves_fields_and_does_not_follow_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        fixture.responses["/api/projects/?page=2&paginate_by=2"] = {
            "count": 7,
            "next": "?page=3&paginate_by=2",
            "previous": "?page=1&paginate_by=2",
            "results": [{"id": 3}, {"id": 4}],
            "future": {"keep": True},
        }
        result = anyio.run(
            call,
            paginated_request(
                "projects/",
                PageSelection(page=2, page_size=2),
                page_size_supported=True,
            ),
        )

    assert fixture.requests == [("GET", "/api/projects/?page=2&paginate_by=2", None)]
    assert isinstance(result, dict)
    assert result["count"] == 7
    assert result["future"] == {"keep": True}
    assert result["results"] == [{"id": 3}, {"id": 4}]
    assert result["pagination"] == {
        "mode": "native_page",
        "page": 2,
        "page_size": 2,
        "returned_count": 2,
        "native_total": 7,
        "native_total_scope": "collection",
        "filtered_total": None,
        "filtered_total_scope": "not_filtered",
        "has_next": True,
        "has_previous": True,
        "next_page": 3,
        "previous_page": 1,
        "collection_consistency": "snapshot_not_guaranteed",
    }


def test_page_two_accepts_canonical_previous_link_without_page_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        fixture.responses["/api/projects/?page=2"] = {
            "count": 3,
            "next": "?page=3",
            "previous": fixture.url.rstrip("/") + "/api/projects/",
            "results": [{"id": 2}],
        }
        result = anyio.run(
            call,
            paginated_request(
                "projects/", PageSelection(page=2), page_size_supported=True
            ),
        )
    assert isinstance(result, dict)
    metadata = result["pagination"]
    assert isinstance(metadata, dict)
    assert metadata["previous_page"] == 1


@pytest.mark.parametrize(
    "case",
    [
        (
            1,
            {"count": 3, "next": "?page=2", "previous": None, "results": [1]},
            2,
            None,
            "collection",
        ),
        (
            3,
            {"count": 3, "next": None, "previous": "?page=2", "results": [3]},
            None,
            2,
            "collection",
        ),
        (
            1,
            {"next": None, "previous": None, "results": []},
            None,
            None,
            "unknown",
        ),
        (
            1,
            {"count": -1, "next": None, "previous": None, "results": [1]},
            None,
            None,
            "unknown",
        ),
    ],
)
def test_first_final_and_empty_native_pages(
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[int, JsonValue, int | None, int | None, str],
) -> None:
    page, response, next_page, previous_page, native_scope = case
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        route = f"/api/projects/?page={page}"
        fixture.responses[route] = response
        result = anyio.run(
            call,
            paginated_request(
                "projects/", PageSelection(page=page), page_size_supported=True
            ),
        )
    assert fixture.requests == [("GET", route, None)]
    assert isinstance(result, dict)
    metadata = result["pagination"]
    assert isinstance(metadata, dict)
    assert metadata["next_page"] == next_page
    assert metadata["previous_page"] == previous_page
    assert metadata["native_total_scope"] == native_scope


def test_empty_unknown_total_and_filtered_page_metadata_are_honest() -> None:
    raw: JsonValue = {
        "next": None,
        "previous": "?page=1",
        "results": [{"id": 3, "state": "done"}, {"id": 4, "state": "running"}],
        "pagination": {
            "mode": "native_page",
            "page": 2,
            "page_size": None,
            "returned_count": 2,
            "native_total": None,
            "native_total_scope": "unknown",
            "filtered_total": None,
            "filtered_total_scope": "not_filtered",
            "has_next": False,
            "has_previous": True,
            "next_page": None,
            "previous_page": 1,
            "collection_consistency": "snapshot_not_guaranteed",
        },
    }
    filtered = annotate_filtered_page(raw, [{"id": 3, "state": "done"}])
    assert isinstance(filtered, dict)
    assert filtered["count"] is None
    assert filtered["results"] == [{"id": 3, "state": "done"}]
    metadata = filtered["pagination"]
    assert isinstance(metadata, dict)
    assert metadata["returned_count"] == 1
    assert metadata["native_total"] is None
    assert metadata["filtered_total"] == 1
    assert metadata["filtered_total_scope"] == "source_page"
