"""Account identity and staff permissions are checked without broadening visibility."""

import anyio
import pytest
from pydantic import JsonValue

from tests.account_fixture import (
    CURRENT,
    OTHER,
    SELF,
    AccountFixture,
    account_fixture,
    account_session,
)


@pytest.mark.parametrize("tool", ["create_user", "delete_user"])
def test_invitation_capability_does_not_authorize_staff_operations(tool: str) -> None:
    # Given can_invite=true but is_staff=false on the acting user.
    args: dict[str, JsonValue] = (
        {"user_id": 1}
        if tool == "delete_user"
        else {"account": {"username": "New", "email": "new@example.org"}}
    )

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When trying staff-only account creation or deletion.
            result = await session.call_tool(tool, args)
            # Then invitation capability cannot authorize a staff-only operation.
            assert result.is_error

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", CURRENT, None)]


@pytest.mark.parametrize(
    ("tool", "record"),
    [
        ("get_current_user", {"pk": "1"}),
        ("get_current_user", {"pk": 0}),
        ("get_user", {"pk": 2}),
        ("update_user", {"pk": 2}),
        ("create_user", {"pk": 1, "is_staff": "true"}),
        ("delete_user", {"pk": 1, "is_staff": 1}),
    ],
)
def test_malformed_or_wrong_identity_cannot_authorize_account_access(
    tool: str, record: JsonValue
) -> None:
    # Given malformed capability metadata or a different detail primary key.
    args: dict[str, JsonValue] = {}
    if tool in {"get_user", "update_user", "delete_user"}:
        args["user_id"] = 1
    if tool == "update_user":
        args["changes"] = {"first_name": "Changed"}
    if tool == "create_user":
        args["account"] = {"username": "New", "email": "new@example.org"}

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When those records are used by a read or write preflight.
            result = await session.call_tool(tool, args)
            # Then no account mutation is allowed from invalid authority.
            assert result.is_error

    with account_fixture() as fixture:
        fixture.responses[SELF if tool in {"get_user", "update_user"} else CURRENT] = (
            record
        )
        anyio.run(run, fixture)
    assert all(r[0] == "GET" for r in fixture.requests)


def test_nonstaff_cannot_update_hidden_other_account() -> None:
    # Given a nonstaff account outside another user's self-only queryset.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When requesting an edit to the hidden target.
            result = await session.call_tool(
                "update_user",
                {"user_id": 2, "changes": {"email": "other-new@example.org"}},
            )
            # Then the scoped detail failure blocks the PATCH.
            assert result.is_error

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", OTHER, None)]
