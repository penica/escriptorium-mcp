"""Pagination remains within the authenticated downloads collection."""

import anyio
import pytest

from tests.download_fixture import (
    COLLECTION,
    DownloadFixture,
    download_fixture,
    download_session,
)


@pytest.mark.parametrize(
    "suffix",
    [
        "api/tasks/?page=2",
        "downloads/?page=2",
        "api/downloads/../tasks/?page=2",
        "api/downloads/%2e%2e/tasks/?page=2",
        "api/%64ownloads/?page=2",
        "api/downloads/?page=2#fragment",
        "api/downloads/\\../tasks/?page=2",
        "api/downloads/other/?page=2",
    ],
)
def test_next_link_cannot_leave_collection(suffix: str) -> None:
    with download_fixture() as fixture:
        fixture.responses[COLLECTION] = {
            "count": 2,
            "next": fixture.url + suffix,
            "results": [fixture.detail],
        }
        anyio.run(expect_failure, fixture)
    assert fixture.requests == [("GET", COLLECTION)]


async def expect_failure(fixture: DownloadFixture) -> None:
    async with download_session(fixture) as session:
        response = await session.call_tool("list_downloads", {})
        assert response.is_error
        assert "fixture-key" not in str(response.content)


def test_foreign_next_receives_no_request() -> None:
    with download_fixture() as fixture, download_fixture() as foreign:
        fixture.responses[COLLECTION] = {
            "count": 2,
            "next": foreign.url + "api/downloads/?page=2",
            "results": [fixture.detail],
        }
        anyio.run(expect_failure, fixture)
    assert fixture.requests == [("GET", COLLECTION)]
    assert not foreign.requests


def test_userinfo_next_is_rejected() -> None:
    with download_fixture() as fixture:
        fixture.responses[COLLECTION] = {
            "count": 2,
            "next": fixture.url.replace("http://", "http://user:password@")
            + "api/downloads/?page=2",
            "results": [fixture.detail],
        }
        anyio.run(expect_failure, fixture)
    assert fixture.requests == [("GET", COLLECTION)]


def test_pagination_cycle_is_rejected_without_repeat() -> None:
    with download_fixture() as fixture:
        fixture.responses[COLLECTION] = {
            "count": 2,
            "next": "?page=2",
            "results": [fixture.detail],
        }
        fixture.responses[COLLECTION + "?page=2"] = {
            "count": 2,
            "next": fixture.url + "api/downloads/",
            "results": [],
        }
        anyio.run(expect_failure, fixture)
    assert fixture.requests == [("GET", COLLECTION), ("GET", COLLECTION + "?page=2")]


def test_second_page_redirect_does_not_forward_token() -> None:
    with download_fixture() as fixture, download_fixture() as foreign:
        fixture.responses[COLLECTION] = {
            "count": 2,
            "next": "?page=2",
            "results": [fixture.detail],
        }
        fixture.redirects[COLLECTION + "?page=2"] = foreign.url + "api/downloads/"
        anyio.run(expect_failure, fixture)
    assert fixture.requests == [("GET", COLLECTION), ("GET", COLLECTION + "?page=2")]
    assert not foreign.requests
