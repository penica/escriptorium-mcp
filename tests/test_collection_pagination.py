"""Collection pagination opts into scoped URLs without changing legacy requests."""

from dataclasses import replace
from typing import TYPE_CHECKING

import anyio
import pytest

from escriptorium_mcp.api import ApiRequest
from tests.collection_fixture import (
    COLLECTION,
    COLLECTIONS,
    ITEMS,
    CollectionFixture,
    collection_fixture,
    collection_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_strict_pagination_opt_in_is_serialized() -> None:
    request = ApiRequest.model_validate(
        {
            "method": "GET",
            "route": "collections/",
            "paginate": True,
            "strict_pagination": True,
        }
    )
    assert request.model_dump(exclude_none=True)["strict_pagination"] is True


def test_legacy_api_request_omits_strict_pagination() -> None:
    request = ApiRequest(method="GET", route="projects/", paginate=True)
    assert "strict_pagination" not in request.model_dump(exclude_none=True)


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
@pytest.mark.parametrize("bare", [False, True])
def test_collection_reads_preserve_raw_shapes(tool: str, *, bare: bool) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    args: dict[str, JsonValue] = (
        {} if tool == "list_collections" else {"collection_id": 7}
    )
    first: dict[str, JsonValue] = {"id": 1, "unknown": None, "zero": 0}
    second: dict[str, JsonValue] = {"id": 2, "unknown": {"keep": True}}
    with collection_fixture() as fixture:
        fixture.responses[route] = [first, second]
        if not bare:
            fixture.responses[route] = {
                "count": 17,
                "next": "?page=2",
                "previous": "preserve previous",
                "results": [first],
                "extra": "keep",
            }
            fixture.responses[route + "?page=2"] = {
                "count": 17,
                "next": None,
                "results": [second],
            }

        async def run() -> None:
            async with collection_session(fixture) as session:
                result = await invoke(session, tool, args)
                expected: JsonValue = (
                    [first, second]
                    if bare
                    else {
                        "count": 17,
                        "next": None,
                        "previous": "preserve previous",
                        "results": [first, second],
                        "extra": "keep",
                    }
                )
                assert result == expected

        anyio.run(run)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    expected_requests = [*prefix, ("GET", route, None)]
    if not bare:
        expected_requests.append(("GET", route + "?page=2", None))
    assert fixture.requests == expected_requests


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
@pytest.mark.parametrize(
    "suffix",
    [
        "api/documents/?page=2",
        "api/collections/8/items/?page=2",
        "collections/?page=2",
        "api/collections/../documents/?page=2",
        "api/collections/%2e%2e/documents/?page=2",
        "api/%63ollections/?page=2",
        "api/collections/\\../documents/?page=2",
    ],
)
def test_next_links_cannot_substitute_routes(tool: str, suffix: str) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    with collection_fixture() as fixture:
        fixture.responses[route] = {
            "count": 2,
            "next": fixture.url + suffix,
            "results": [],
        }
        anyio.run(expect_rejected_read, fixture, tool)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    assert fixture.requests == [*prefix, ("GET", route, None)]


async def expect_rejected_read(fixture: CollectionFixture, tool: str) -> None:
    args: dict[str, JsonValue] = (
        {} if tool == "list_collections" else {"collection_id": 7}
    )
    async with collection_session(fixture) as session:
        result = await session.call_tool(tool, args)
        assert result.is_error
        assert "fixture-key" not in str(result.content)


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
@pytest.mark.parametrize("decoration", ["fragment", "userinfo", "control"])
def test_same_path_url_decorations_are_rejected(tool: str, decoration: str) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    with collection_fixture() as fixture:
        absolute = fixture.url.rstrip("/") + route + "?page=2"
        decorated = {
            "fragment": absolute + "#fragment",
            "userinfo": absolute.replace("http://", "http://user:secret@"),
            "control": "\n" + absolute,
        }
        fixture.responses[route] = {
            "count": 2,
            "next": decorated[decoration],
            "results": [],
        }
        anyio.run(expect_rejected_read, fixture, tool)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    assert fixture.requests == [*prefix, ("GET", route, None)]


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
def test_foreign_next_never_receives_credentials(tool: str) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    with collection_fixture() as fixture, collection_fixture() as foreign:
        fixture.responses[route] = {
            "count": 2,
            "next": foreign.url.rstrip("/") + route,
            "results": [],
        }
        anyio.run(expect_rejected_read, fixture, tool)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    assert fixture.requests == [*prefix, ("GET", route, None)]
    assert not foreign.received
    assert not foreign.requests


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
@pytest.mark.parametrize("later_page", [False, True])
def test_redirects_are_refused_on_every_page(tool: str, *, later_page: bool) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    with collection_fixture() as fixture, collection_fixture() as foreign:
        redirect_route = route
        if later_page:
            fixture.responses[route] = {"count": 2, "next": "?page=2", "results": []}
            redirect_route += "?page=2"
        fixture.redirects[redirect_route] = foreign.url.rstrip("/") + route
        anyio.run(expect_rejected_read, fixture, tool)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    expected = [*prefix, ("GET", route, None)]
    if later_page:
        expected.append(("GET", redirect_route, None))
    assert fixture.requests == expected
    assert not foreign.received
    assert not foreign.requests


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
def test_pagination_cycle_is_refused_before_repeated_fetch(tool: str) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    with collection_fixture() as fixture:
        fixture.responses[route] = {"count": 2, "next": "?page=2", "results": []}
        fixture.responses[route + "?page=2"] = {
            "count": 2,
            "next": fixture.url.rstrip("/") + route,
            "results": [],
        }
        anyio.run(expect_rejected_read, fixture, tool)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    assert fixture.requests == [
        *prefix,
        ("GET", route, None),
        ("GET", route + "?page=2", None),
    ]


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
@pytest.mark.parametrize("escape_prefix", [False, True])
def test_configured_path_prefix_is_preserved(tool: str, *, escape_prefix: bool) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    scoped_route = "/workspace" + route
    args: dict[str, JsonValue] = (
        {} if tool == "list_collections" else {"collection_id": 7}
    )
    with collection_fixture() as fixture:
        prefixed = replace(fixture, url=fixture.url + "workspace/")
        fixture.responses["/workspace" + COLLECTION] = fixture.collection
        fixture.responses[scoped_route] = {
            "count": 0,
            "next": route + "?page=2" if escape_prefix else "?page=2",
            "results": [],
        }
        fixture.responses[scoped_route + "?page=2"] = {
            "count": 0,
            "next": None,
            "results": [],
        }

        async def run() -> None:
            async with collection_session(prefixed) as session:
                response = await session.call_tool(tool, args)
                assert response.is_error is escape_prefix

        anyio.run(run)
    prefix = (
        [] if tool == "list_collections" else [("GET", "/workspace" + COLLECTION, None)]
    )
    expected = [*prefix, ("GET", scoped_route, None)]
    if not escape_prefix:
        expected.append(("GET", scoped_route + "?page=2", None))
    assert fixture.requests == expected


@pytest.mark.parametrize("tool", ["list_collections", "list_collection_items"])
def test_redirect_status_without_location_is_also_refused(tool: str) -> None:
    route = COLLECTIONS if tool == "list_collections" else ITEMS
    with collection_fixture() as fixture:
        fixture.failures[route] = 300
        anyio.run(expect_rejected_read, fixture, tool)
    prefix = [] if tool == "list_collections" else [("GET", COLLECTION, None)]
    assert fixture.requests == [*prefix, ("GET", route, None)]
