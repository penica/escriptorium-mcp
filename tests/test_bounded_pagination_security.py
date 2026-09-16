from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import call
from escriptorium_mcp.pagination import PageSelection, paginated_request
from tests.collection_fixture import collection_fixture
from tests.page_fixture import PageFixture, page_fixture, page_session

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize("link", ["next", "previous"])
@pytest.mark.parametrize(
    "target",
    [
        "http://example.invalid/api/projects/?page=2",
        "/api/documents/?page=2",
        "?page=bad",
        "?page=1&page=2",
        "?page=1#fragment",
        "?page=1&cursor=secret",
    ],
)
def test_every_continuation_is_validated_without_following(
    monkeypatch: pytest.MonkeyPatch, link: str, target: str
) -> None:
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        fixture.responses["/api/projects/?page=1"] = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [{"id": 1}],
            link: target,
        }
        with pytest.raises(ToolError):
            _ = anyio.run(
                call,
                paginated_request(
                    "projects/", PageSelection(), page_size_supported=True
                ),
            )
    assert fixture.requests == [("GET", "/api/projects/?page=1", None)]


def test_self_link_and_bare_list_are_rejected_honestly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: tuple[JsonValue, ...] = (
        {"count": 1, "next": "?page=1", "previous": None, "results": []},
        [{"id": 1}],
    )
    for response in responses:
        with collection_fixture() as fixture:
            monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
            monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
            fixture.responses["/api/projects/?page=1"] = response
            with pytest.raises(ToolError):
                _ = anyio.run(
                    call,
                    paginated_request(
                        "projects/", PageSelection(), page_size_supported=True
                    ),
                )


@pytest.mark.parametrize(
    "query",
    [{}, {"page": "0"}, {"page": "bad"}, {"page": "1", "paginate_by": "51"}],
)
def test_private_invalid_page_query_fails_before_http(
    monkeypatch: pytest.MonkeyPatch, query: dict[str, str]
) -> None:
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        with pytest.raises(ToolError):
            _ = anyio.run(
                call,
                ApiRequest(
                    method="GET",
                    route="projects/",
                    native_page=True,
                    strict_pagination=True,
                    query=query,
                ),
            )
    assert not fixture.requests


def test_native_page_http_error_is_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with collection_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        route = "/api/projects/?page=2"
        fixture.failures[route] = 500
        with pytest.raises(ToolError):
            _ = anyio.run(
                call,
                paginated_request(
                    "projects/", PageSelection(page=2), page_size_supported=True
                ),
            )
    assert fixture.requests == [("GET", route, None)]


def test_unsupported_page_size_is_explicit_through_mcp() -> None:
    async def run(fixture: PageFixture) -> None:
        async with page_session(fixture) as session:
            response = await session.call_tool(
                "list_pages",
                {"document_id": 4, "pagination": {"page": 1, "page_size": 2}},
            )
            assert response.is_error
            assert "documents/4/parts/ does not support page_size." in str(
                response.content
            )

    with page_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
