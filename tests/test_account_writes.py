"""Explicit account writes preserve native settings and never retry mutations."""

from typing import TYPE_CHECKING

import anyio
import pytest

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


def test_staff_create_keeps_unicode_and_omits_unsupplied_defaults() -> None:
    # Given a staff account authorized to create native account rows.
    account: dict[str, JsonValue] = {
        "username": "Žan.@+_-",
        "email": "MixedCase@example.org",
    }

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When only required username and email are supplied.
            result = await invoke(session, "create_user", {"account": account})
            # Then acceptance remains raw without password/invitation success claims.
            assert result == {"pk": 2, "saved": account}

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", CURRENT, None), ("POST", USERS, account)]


def test_self_email_and_display_names_are_editable_without_staff() -> None:
    # Given a nonstaff user editing their own email and deliberately clearing names.
    changes: dict[str, JsonValue] = {
        "email": "new@example.org",
        "first_name": "",
        "last_name": "",
    }

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When native self-edit permissions authorize the account change.
            result = await invoke(
                session, "update_user", {"user_id": 1, "changes": changes}
            )
            # Then the native result is returned without an invented staff-only policy.
            assert result == {"pk": 1, "saved": changes}

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", SELF, None), ("PATCH", SELF, changes)]


def test_self_deactivation_is_false_and_has_no_followup_read() -> None:
    # Given an intentional mutation that can invalidate the caller's authentication.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When the current user explicitly deactivates their account.
            result = await invoke(
                session, "update_user", {"user_id": 1, "changes": {"is_active": False}}
            )
            # Then explicit false survives without reauthentication.
            assert result == {"pk": 1, "saved": {"is_active": False}}

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", SELF, None),
        ("PATCH", SELF, {"is_active": False}),
    ]


@pytest.mark.parametrize("user_id", [1, 2])
def test_staff_delete_uses_bodyless_success_without_post_delete_query(
    user_id: int,
) -> None:
    # Given a staff user deleting themselves or another visible account.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When the explicit deletion is performed once.
            result = await invoke(session, "delete_user", {"user_id": user_id})
            # Then native 204 survives even if the caller loses authentication.
            assert result == {"status": "success", "http_status": 204}

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        anyio.run(run, fixture)
    expected = [("GET", CURRENT, None)]
    if user_id == 2:
        expected.append(("GET", OTHER, None))
    assert fixture.requests == [
        *expected,
        ("DELETE", SELF if user_id == 1 else OTHER, {}),
    ]


@pytest.mark.parametrize("action", ["create", "update", "delete"])
@pytest.mark.parametrize("failure", ["server", "disconnect"])
def test_account_write_is_never_retried(action: str, failure: str) -> None:
    # Given a server error or lost response after a possibly completed account mutation.
    calls: dict[str, tuple[str, dict[str, JsonValue], str]] = {
        "create": (
            "create_user",
            {"account": {"username": "New", "email": "new@example.org"}},
            "POST " + USERS,
        ),
        "update": (
            "update_user",
            {"user_id": 1, "changes": {"is_active": False}},
            "PATCH " + SELF,
        ),
        "delete": ("delete_user", {"user_id": 1}, "DELETE " + SELF),
    }
    tool, args, key = calls[action]

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When one administrative write fails ambiguously.
            result = await session.call_tool(tool, args)
            # Then no duplicate mutation or credential-bearing error is returned.
            assert result.is_error
            assert "fixture-key" not in result.model_dump_json()

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        if failure == "server":
            fixture.failures[key] = 500
        else:
            fixture.disconnect.add(key)
        anyio.run(run, fixture)
    assert len([r for r in fixture.requests if r[0] != "GET"]) == 1
    assert len(fixture.requests) == 2


def test_full_email_syntax_validation_remains_native() -> None:
    # Given bounded nonblank email text rejected by the native Django serializer.
    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When creation is delegated to the native account endpoint.
            result = await session.call_tool(
                "create_user",
                {
                    "account": {
                        "username": "New",
                        "email": "native-must-validate",
                    }
                },
            )
            # Then its validation error survives, with no automatic correction or retry.
            assert result.is_error

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        fixture.failures["POST " + USERS] = 400
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", USERS, {"username": "New", "email": "native-must-validate"}),
    ]


def test_staff_explicit_create_settings_and_other_account_update() -> None:
    # Given staff permission and explicitly supplied native account settings.
    account: dict[str, JsonValue] = {
        "username": "Ž" * 150,
        "email": "new@example.org",
        "first_name": "",
        "last_name": "Surname",
        "is_active": False,
    }

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            # When creating a disabled account and renaming a different visible user.
            created = await invoke(session, "create_user", {"account": account})
            assert created == {"pk": 2, "saved": account}
            changed = await invoke(
                session,
                "update_user",
                {
                    "user_id": 2,
                    "changes": {"username": "Other.Ž"},
                },
            )
            # Then false/blank settings and staff editing permission survive.
            assert isinstance(changed, dict)
            assert changed["pk"] == 2
            assert changed["saved"] == {"username": "Other.Ž"}

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", USERS, account),
        ("GET", OTHER, None),
        ("PATCH", OTHER, {"username": "Other.Ž"}),
    ]
