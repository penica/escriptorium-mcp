"""Group directories search only fully fetched membership-visible native rows."""

import anyio
import pytest

from tests.group_fixture import (
    GROUP,
    GROUPS,
    GroupFixture,
    group_fixture,
    group_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("paginated", [True, False])
def test_group_list_preserves_unfiltered_native_representation(
    *, paginated: bool
) -> None:
    # Given membership-visible groups with unknown fields and null ownership.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When the directory is requested without a local filter.
            result = await invoke(session, "list_groups", {})
            # Then all rows and the native envelope shape survive.
            expected = (
                {
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "custom": "envelope",
                    "results": fixture.rows,
                }
                if paginated
                else fixture.rows
            )
            assert result == expected

    with group_fixture(paginated=paginated) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[0] == ("GET", GROUPS, None)
    assert len(fixture.requests) == (2 if paginated else 1)


def test_group_search_casefolds_locally_after_all_pages() -> None:
    # Given a Unicode match on the second native page.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When the client searches with casefold-equivalent spelling.
            result = await invoke(session, "list_groups", {"search": "STRASSE"})
            # Then the result is local, complete and retains unmodified row fields.
            assert result == {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [fixture.rows[1]],
            }

    with group_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", GROUPS, None),
        ("GET", GROUPS + "?page=2", None),
    ]


def test_group_search_tolerates_missing_or_null_names() -> None:
    # Given directory records without useful searchable names.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When a local name search finds nothing.
            result = await invoke(session, "list_groups", {"search": "absent"})
            # Then no names are invented in the empty normalized envelope.
            assert result == {"count": 0, "next": None, "previous": None, "results": []}

    with group_fixture(paginated=False) as fixture:
        fixture.rows[:] = [{"pk": 6}, {"pk": 7, "name": None}]
        anyio.run(run, fixture)


def test_get_group_preserves_member_list_and_unknown_fields() -> None:
    # Given a readable group with a creator who is not the owner.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When its native detail is retrieved.
            result = await invoke(session, "get_group", {"group_id": 7})
            # Then no owner-only read policy discards its native metadata.
            assert result == fixture.group

    with group_fixture() as fixture:
        fixture.group["owner"] = 99
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", GROUP, None)]
