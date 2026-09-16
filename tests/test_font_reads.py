"""Font catalogue reads preserve native metric metadata without fetching binaries."""

import anyio
import pytest
from pydantic import JsonValue

from tests.font_fixture import FONT, FONTS, FontFixture, font_fixture, font_session
from tests.transcription_fixture import invoke


def test_font_detail_preserves_all_native_fields() -> None:
    # Given native metrics with nullable, zero, negative and future field values.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When reading metadata for a requested font primary key.
            result = await invoke(session, "get_font", {"font_id": 3})
            # Then the complete native record remains unchanged.
            assert result == fixture.font

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", FONT, None)]


def test_font_list_follows_all_pages_without_fetching_metadata_urls() -> None:
    # Given multiple catalogue pages with a foreign storage URL in native metadata.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the authenticated client reads the complete font catalogue.
            result = await invoke(session, "list_fonts", {})
            # Then all rows/count/extras survive and URL fields remain inert metadata.
            assert result == {
                "count": 2,
                "next": None,
                "previous": None,
                "future": 0,
                "results": [fixture.font, {"pk": 4, "name": "Other", "url": None}],
            }

    with font_fixture() as fixture, font_fixture() as storage:
        fixture.font["url"] = storage.url + "font.woff2"
        fixture.responses[FONTS] = {
            "count": 2,
            "next": "?page=2",
            "previous": None,
            "future": 0,
            "results": [fixture.font],
        }
        fixture.responses[FONTS + "?page=2"] = {
            "next": None,
            "results": [{"pk": 4, "name": "Other", "url": None}],
        }
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", FONTS, None), ("GET", FONTS + "?page=2", None)]
    assert not storage.received


def test_bare_and_empty_font_catalogues_retain_native_shapes() -> None:
    # Given catalogue shape variations permitted by the existing raw adapter.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When a bare list and then an empty native envelope are returned.
            fixture.responses[FONTS] = [fixture.font]
            assert await invoke(session, "list_fonts", {}) == [fixture.font]
            fixture.responses[FONTS] = {"count": 0, "next": None, "results": []}
            # Then an empty catalogue is not confused with API unavailability.
            assert await invoke(session, "list_fonts", {}) == {
                "count": 0,
                "next": None,
                "results": [],
            }

    with font_fixture() as fixture:
        anyio.run(run, fixture)


@pytest.mark.parametrize(
    ("tool", "route", "status"),
    [
        ("list_fonts", FONTS, 404),
        ("list_fonts", FONTS, 403),
        ("get_font", FONT, 404),
        ("get_font", FONT, 403),
    ],
)
def test_font_access_errors_are_not_successful_empty_results(
    tool: str, route: str, status: int
) -> None:
    # Given missing or inaccessible font API records.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When catalogue or detail retrieval fails natively.
            result = await session.call_tool(
                tool, {"font_id": 3} if tool == "get_font" else {}
            )
            # Then errors remain errors rather than fabricated empty metadata.
            assert result.is_error

    with font_fixture() as fixture:
        fixture.failures[route] = status
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", route, None)]


@pytest.mark.parametrize("metadata", [{"pk": 4}, {"pk": "3"}, {"pk": True}, {}])
def test_font_detail_checks_exact_native_identity(metadata: JsonValue) -> None:
    # Given a detail response with a different or malformed primary key.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the client requests font3.
            result = await session.call_tool("get_font", {"font_id": 3})
            # Then that record cannot be mistaken for the requested font.
            assert result.is_error

    with font_fixture() as fixture:
        fixture.responses[FONT] = metadata
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", FONT, None)]


@pytest.mark.parametrize(
    "next_link",
    [
        "/api/projects/",
        "/api/fonts/3/",
        "/api/fonts/../projects/",
        "/api/fonts/%2e%2e/projects/",
        "/api/fonts/?page=2#fragment",
        "/api/fonts/",
    ],
)
def test_font_pagination_refuses_route_substitution_and_loops(next_link: str) -> None:
    # Given a next link outside the font collection or back to an already-read page.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When strict catalogue traversal sees the malformed next link.
            result = await session.call_tool("list_fonts", {})
            # Then no unrelated authenticated route is fetched.
            assert result.is_error

    with font_fixture() as fixture:
        fixture.responses[FONTS] = {
            "count": 2,
            "next": next_link,
            "results": [fixture.font],
        }
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", FONTS, None)]


def test_foreign_font_pagination_never_contacts_other_origin() -> None:
    # Given pagination pointing to a separate listener.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When a foreign continuation URL is encountered.
            result = await session.call_tool("list_fonts", {})
            # Then it is refused before any foreign network connection.
            assert result.is_error

    with font_fixture() as fixture, font_fixture() as foreign:
        fixture.responses[FONTS] = {
            "count": 2,
            "next": foreign.url + "api/fonts/",
            "results": [fixture.font],
        }
        anyio.run(run, fixture)
    assert not foreign.received
    assert fixture.requests == [("GET", FONTS, None)]


@pytest.mark.parametrize("second_page", [False, True])
def test_font_pagination_does_not_follow_redirects(*, second_page: bool) -> None:
    # Given a redirect at the initial catalogue or one of its continuation pages.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the catalogue fetch receives HTTP302.
            result = await session.call_tool("list_fonts", {})
            # Then the storage/server redirect is never followed with authentication.
            assert result.is_error

    with font_fixture() as fixture, font_fixture() as foreign:
        path = FONTS + "?page=2" if second_page else FONTS
        if second_page:
            fixture.responses[FONTS] = {
                "count": 2,
                "next": "?page=2",
                "results": [fixture.font],
            }
        fixture.redirects[path] = foreign.url + "api/fonts/"
        anyio.run(run, fixture)
    assert not foreign.received
    expected = [("GET", FONTS, None)]
    if second_page:
        expected.append(("GET", FONTS + "?page=2", None))
    assert fixture.requests == expected
