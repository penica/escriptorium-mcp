"""Visible account reads retain native metadata and use local directory search."""

from typing import TYPE_CHECKING

import anyio

from tests.account_fixture import (
    CURRENT,
    OTHER,
    SELF,
    USERS,
    AccountFixture,
    account_fixture,
    account_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_current_account_preserves_native_fields() -> None:
    # Given a current account with capability, null, date and future metadata.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When reading the acting account without requiring OPTIONS support.
            result = await invoke(session, "get_current_user", {})
            # Then the native representation is not synthesized or narrowed.
            assert result == fixture.current

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", CURRENT, None)]


def test_nonstaff_directory_is_self_only_and_detail_errors_remain_errors() -> None:
    # Given native nonstaff visibility containing only the acting account.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When listing visible users, including a null optional search.
            variants: list[dict[str, JsonValue]] = [{}, {"search": None}]
            for arguments in variants:
                result = await invoke(session, "list_users", arguments)
                assert result == {
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [fixture.current],
                }
            assert await invoke(session, "get_user", {"user_id": 1}) == fixture.current
            # Then an inaccessible different user is an error, not a discoverable row.
            inaccessible = await session.call_tool("get_user", {"user_id": 2})
            assert inaccessible.is_error

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", USERS, None),
        ("GET", USERS, None),
        ("GET", SELF, None),
        ("GET", OTHER, None),
    ]


def test_local_unicode_casefold_search_reads_all_visible_pages_without_query() -> None:
    # Given a visible second-page username that matches only after Unicode casefold.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When users are locally searched after complete native pagination.
            result = await invoke(session, "list_users", {"search": "STRASSE"})
            # Then the local count reflects matches and the row itself is unchanged.
            assert result == {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [fixture.other],
            }
            full = await invoke(session, "list_users", {})
            assert full == {
                "count": 9,
                "next": None,
                "previous": "retained",
                "future": 0,
                "results": [fixture.current, fixture.other],
            }

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        fixture.responses[USERS] = {
            "count": 9,
            "next": "?page=2",
            "previous": "retained",
            "future": 0,
            "results": [fixture.current],
        }
        fixture.responses[USERS + "?page=2"] = {
            "next": None,
            "results": [fixture.other],
        }
        anyio.run(run, fixture)
    assert [r[1] for r in fixture.requests] == [USERS, USERS + "?page=2"] * 2


def test_bare_directory_search_tolerates_absent_nullable_names() -> None:
    # Given raw rows with omitted names and nullable searchable metadata.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When a local email substring is searched across that collection.
            result = await invoke(session, "list_users", {"search": "EXAMPLE.ORG"})
            assert result == {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [fixture.other],
            }
            # Then no-search output keeps its native bare-list shape.
            assert await invoke(session, "list_users", {}) == [fixture.other, {"pk": 3}]

    with account_fixture() as fixture:
        fixture.responses[USERS] = [fixture.other, {"pk": 3}]
        anyio.run(run, fixture)
    assert all(r[1] == USERS for r in fixture.requests)
