"""Opt-in native page selection for public catalogue tools."""

from typing import TYPE_CHECKING, Final

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp.pagination import NativePage
from escriptorium_mcp.server import create_server
from tests.account_fixture import USERS, AccountFixture, account_fixture
from tests.collection_fixture import (
    COLLECTION,
    ITEMS,
    CollectionFixture,
    collection_fixture,
    collection_session,
)
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result, invoke

if TYPE_CHECKING:
    from mcp.types import Tool


PAGED_TOOLS: Final = (
    "list_users",
    "list_groups",
    "list_fonts",
    "list_collections",
    "list_collection_items",
    "list_textual_witnesses",
    "list_metadata",
    "list_tags",
    "list_annotation_components",
    "list_annotation_taxonomies",
    "list_annotations",
    "list_ontology_types",
)


def test_owned_catalogue_schemas_offer_optional_page_selection() -> None:
    # Given the complete in-process MCP catalogue.
    tools: list[Tool] = anyio.run(create_server().list_tools)
    schemas = {tool.name: tool.input_schema for tool in tools}

    # When each owned public catalogue is inspected.
    # Then every list accepts the same optional typed pagination object.
    for name in PAGED_TOOLS:
        schema = TypeAdapter[dict[str, JsonValue]](
            dict[str, JsonValue]
        ).validate_python(schemas[name])
        properties = TypeAdapter[dict[str, JsonValue]](
            dict[str, JsonValue]
        ).validate_python(schema["properties"])
        pagination = TypeAdapter[dict[str, JsonValue]](
            dict[str, JsonValue]
        ).validate_python(properties["pagination"])
        variants = TypeAdapter[list[dict[str, JsonValue]]](
            list[dict[str, JsonValue]]
        ).validate_python(pagination["anyOf"])
        assert pagination["default"] is None
        assert variants[0]["$ref"] == "#/$defs/PageSelection"


async def _exercise_paged_users_http(fixture: AccountFixture) -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When one explicit native user page crosses authenticated MCP HTTP.
        result = await session.call_tool(
            "list_users", {"pagination": {"page": 2, "page_size": 1}}
        )
        # Then only that native page is returned without fetching another page.
        assert decoded_result(result) == {
            "count": 9,
            "next": None,
            "previous": "?page=1&paginate_by=1",
            "results": [fixture.other],
            "pagination": {
                "mode": "native_page",
                "page": 2,
                "page_size": 1,
                "returned_count": 1,
                "native_total": 9,
                "native_total_scope": "collection",
                "filtered_total": None,
                "filtered_total_scope": "not_filtered",
                "has_next": False,
                "has_previous": True,
                "next_page": None,
                "previous_page": 1,
                "collection_consistency": "snapshot_not_guaranteed",
            },
        }
        filtered = await session.call_tool(
            "list_users",
            {
                "search": "no page-two match",
                "pagination": {"page": 2, "page_size": 1},
            },
        )
        assert decoded_result(filtered) == {
            "count": None,
            "next": None,
            "previous": "?page=1&paginate_by=1",
            "results": [],
            "pagination": {
                "mode": "native_page",
                "page": 2,
                "page_size": 1,
                "returned_count": 0,
                "native_total": 9,
                "native_total_scope": "collection",
                "filtered_total": 0,
                "filtered_total_scope": "source_page",
                "has_next": False,
                "has_previous": True,
                "next_page": None,
                "previous_page": 1,
                "collection_consistency": "snapshot_not_guaranteed",
            },
        }
        unsupported_size = await session.call_tool(
            "list_fonts", {"pagination": {"page_size": 1}}
        )
        assert unsupported_size.is_error


def test_user_page_selection_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a staff-visible directory with an isolated second native page.
    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        fixture.responses[USERS + "?page=2&paginate_by=1"] = {
            "count": 9,
            "next": None,
            "previous": "?page=1&paginate_by=1",
            "results": [fixture.other],
        }
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(_exercise_paged_users_http, fixture)
    assert fixture.requests == [
        ("GET", USERS + "?page=2&paginate_by=1", None),
        ("GET", USERS + "?page=2&paginate_by=1", None),
    ]


def test_collection_items_select_documented_native_page_only() -> None:
    # Given the native fixed-size item paginator documented outside its schema fields.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When the public list selects its second native page.
            result = await invoke(
                session,
                "list_collection_items",
                {"collection_id": 7, "pagination": {"page": 2}},
            )
            # Then no page-size override is invented and only page two is returned.
            page = NativePage.model_validate(result)
            assert page.results == [fixture.items[1]]
            assert page.pagination.page == 2
            assert page.pagination.page_size is None

    with collection_fixture() as fixture:
        fixture.responses[ITEMS + "?page=2"] = {
            "count": 2,
            "next": None,
            "previous": ITEMS,
            "results": [fixture.items[1]],
        }
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", COLLECTION, None),
        ("GET", ITEMS + "?page=2", None),
    ]
