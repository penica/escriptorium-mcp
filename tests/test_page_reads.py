"""Page lookup and filtered pagination across actual MCP STDIO."""

from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import anyio
import pytest

from tests.page_fixture import PAGE, PARTS, page_fixture, page_session
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_page_by_order_returns_native_detail() -> None:
    # Given a scoped fixture and actual STDIO server.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When a page is looked up by its zero-based order.
                result = await invoke(
                    session, "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then the complete native detail survives one bounded follow.
                assert result == fixture.rows[0]

        anyio.run(scenario)
    assert [path for _, path, _ in fixture.requests] == [
        PARTS + "byorder/?order=0",
        PAGE,
    ]


@pytest.mark.parametrize(
    "location",
    [
        "/api/documents/9/parts/10/",
        "/api/documents/4/parts/10/?x=1",
        "/api/documents/4/parts/10/#fragment",
        "/api/users/1/",
        "/api/documents/4/parts/0/",
        "/api/documents/4/parts/%31%30/",
        "http://localhost:1/api/documents/4/parts/10/",
    ],
)
def test_lookup_refuses_unsafe_redirect(location: str) -> None:
    # Given an untrusted redirect from the native lookup endpoint.
    with page_fixture() as fixture:
        fixture.locations[PARTS + "byorder/"] = location

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When lookup is requested.
                result = await session.call_tool(
                    "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then no unsafe target is fetched.
                assert result.is_error

        anyio.run(scenario)
    assert len(fixture.requests) == 1


def test_lookup_never_forwards_credentials_to_other_origin() -> None:
    # Given another listening server that would record any leaked token request.
    with page_fixture() as foreign, page_fixture() as fixture:
        fixture.locations[PARTS + "byorder/"] = foreign.url.rstrip("/") + PAGE

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When lookup receives a cross-origin location.
                result = await session.call_tool(
                    "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then the call fails without contacting that origin.
                assert result.is_error

        anyio.run(scenario)
        assert foreign.requests == []


@pytest.mark.parametrize("status", [200, 403, 404])
def test_lookup_native_errors_are_mcp_errors(status: int) -> None:
    # Given an out-of-bounds body or HTTP permission/missing response.
    with page_fixture() as fixture:
        fixture.failures[PARTS + "byorder/"] = status

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the native lookup fails.
                result = await session.call_tool(
                    "get_page_by_order", {"document_id": 4, "order": 99}
                )
                # Then it is not reported as a successful page record.
                assert result.is_error

        anyio.run(scenario)
    assert len(fixture.requests) == 1


def test_lookup_refuses_second_redirect() -> None:
    # Given the safe target redirects back to the lookup.
    with page_fixture() as fixture:
        fixture.locations[PAGE] = PARTS + "byorder/"

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the first redirect is followed.
                result = await session.call_tool(
                    "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then the second redirect terminates the read.
                assert result.is_error

        anyio.run(scenario)
    assert len(fixture.requests) == 2


@pytest.mark.parametrize("filtered", [False, True])
def test_pagination_preserves_native_fields_and_filters(*, filtered: bool) -> None:
    # Given multiple native result pages with modern fields.
    with page_fixture(paginated=True) as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                args: dict[str, JsonValue] = {
                    "document_id": 4,
                    **(
                        {"filters": {"name": "č scan", "ordering": ["-order", "name"]}}
                        if filtered
                        else {}
                    ),
                }
                # When all pages are requested.
                result = await invoke(session, "list_pages", args)
                # Then all native rows and nested fields are preserved.
                assert isinstance(result, dict)
                assert result["results"] == fixture.rows
                assert result["count"] == len(fixture.rows)
                assert result["next"] is None

        anyio.run(scenario)
    assert len(fixture.requests) == 2
    if filtered:
        for _, path, _ in fixture.requests:
            query = parse_qs(urlsplit(path).query)
            assert query["name"] == ["č scan"]
            assert query["ordering"] == ["-order,name"]


@pytest.mark.parametrize("filtered", [False, True])
def test_pagination_refuses_foreign_next(*, filtered: bool) -> None:
    # Given a paginated upstream response with a foreign next link.
    with page_fixture() as foreign, page_fixture(paginated=True) as fixture:
        fixture.locations["next"] = foreign.url.rstrip("/") + PARTS

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When either legacy or filtered pagination follows results.
                result = await session.call_tool(
                    "list_pages",
                    {
                        "document_id": 4,
                        **({"filters": {"name": "scan"}} if filtered else {}),
                    },
                )
                # Then credentials cannot reach the foreign host.
                assert result.is_error

        anyio.run(scenario)
        assert foreign.requests == []


def test_lookup_refuses_detail_with_mismatched_identity() -> None:
    # Given the valid redirect target returns another page's detail.
    with page_fixture() as fixture:
        fixture.details[PAGE] = {"pk": 11, "name": "wrong page"}

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the redirect is followed once.
                result = await session.call_tool(
                    "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then no unrelated page is returned as the requested order.
                assert result.is_error

        anyio.run(scenario)
    assert len(fixture.requests) == 2


def test_lookup_accepts_absolute_same_origin_redirect() -> None:
    # Given a native absolute URL with the requested document and page route.
    with page_fixture() as fixture:
        fixture.locations[PARTS + "byorder/"] = fixture.url.rstrip("/") + PAGE

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the safe redirect is followed.
                result = await invoke(
                    session, "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then the native detail is preserved.
                assert result == fixture.rows[0]

        anyio.run(scenario)
    assert len(fixture.requests) == 2


@pytest.mark.parametrize("tool", ["get_page", "list_regions"])
def test_legacy_page_reads_preserve_modern_region_fields(tool: str) -> None:
    # Given a modern detail record with region locking and raw geometry.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When existing page readers retrieve the record.
                result = await invoke(session, tool, {"document_id": 4, "page_id": 10})
                # Then nested region data is not erased by a legacy connector DTO.
                rows = result["regions"] if isinstance(result, dict) else result
                assert rows == [
                    {"pk": 21, "locked": True, "box": [[1, 2], [3, 2], [3, 4]]}
                ]

        anyio.run(scenario)


@pytest.mark.parametrize("filtered", [False, True])
def test_pagination_refuses_same_origin_cycle(*, filtered: bool) -> None:
    # Given a next link that returns the same first page indefinitely.
    with page_fixture(paginated=True) as fixture:
        fixture.locations["next"] = fixture.url.rstrip("/") + PARTS

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When pagination encounters the repeated URL.
                result = await session.call_tool(
                    "list_pages",
                    {"document_id": 4, **({"filters": {}} if filtered else {})},
                )
                # Then the read stops with an error rather than hanging.
                assert result.is_error

        anyio.run(scenario)
    assert len(fixture.requests) <= 2


def test_lookup_uses_configured_api_path_prefix() -> None:
    # Given eScriptorium is mounted below a non-root deployment path.
    with page_fixture(prefix="/instance") as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When lookup follows the matching prefixed detail URL.
                result = await invoke(
                    session, "get_page_by_order", {"document_id": 4, "order": 0}
                )
                # Then raw detail is returned under the configured API prefix.
                assert result == fixture.rows[0]

        anyio.run(scenario)
    assert [path for _, path, _ in fixture.requests] == [
        "/instance" + PARTS + "byorder/?order=0",
        "/instance" + PAGE,
    ]


@pytest.mark.parametrize("filtered", [False, True])
def test_pagination_refuses_redirect_from_next_page(*, filtered: bool) -> None:
    # Given a same-origin next page that redirects to another resource.
    with page_fixture(paginated=True) as fixture:
        fixture.locations["next"] = fixture.url.rstrip("/") + PARTS + "next/"
        fixture.locations[PARTS + "next/"] = PAGE

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When pagination fetches that link with redirects disabled.
                result = await session.call_tool(
                    "list_pages",
                    {"document_id": 4, **({"filters": {}} if filtered else {})},
                )
                # Then it refuses to follow the next-page redirect.
                assert result.is_error

        anyio.run(scenario)
    assert [path for _, path, _ in fixture.requests] == [PARTS, PARTS + "next/"]
