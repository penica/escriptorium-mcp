"""Account write models enforce native bounds and reject unsupported privileges."""

from pathlib import Path

import anyio
import pytest
from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.account_models import DirectorySearch, UserCreate, UserPatch
from tests.account_fixture import AccountFixture, account_fixture, account_session


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (UserCreate, {"username": "User"}),
        (UserCreate, {"username": "N" * 151, "email": "a@example.org"}),
        (UserCreate, {"username": " leading", "email": "a@example.org"}),
        (UserCreate, {"username": "newline\n", "email": "a@example.org"}),
        (UserCreate, {"username": "emoji😀", "email": "a@example.org"}),
        (UserCreate, {"username": 123, "email": "a@example.org"}),
        (UserCreate, {"username": "User", "email": "e" * 256}),
        (UserCreate, {"username": "User", "email": "   "}),
        (UserCreate, {"username": "User", "email": None}),
        (UserPatch, {}),
        (UserPatch, {"username": None}),
        (UserPatch, {"email": None}),
        (UserPatch, {"first_name": None}),
        (UserPatch, {"last_name": None}),
        (UserPatch, {"is_active": None}),
        (UserPatch, {"is_active": "false"}),
        (UserPatch, {"is_active": 0}),
        (UserPatch, {"first_name": "N" * 151}),
        (UserPatch, {"last_name": 1}),
    ],
)
def test_invalid_account_fields(
    model: type[BaseModel], data: dict[str, JsonValue]
) -> None:
    # Given out-of-bound native fields, implicit boolean coercion or explicit nulls.
    # When parsing the account write, then unsupported values fail before requests.
    with pytest.raises(ValidationError):
        _ = model.model_validate(data)


def test_readonly_privilege_password_and_invitation_fields_are_forbidden() -> None:
    # Given fields absent or read-only in the native account serializer.
    for key in (
        "pk",
        "is_staff",
        "is_superuser",
        "permissions",
        "groups",
        "password",
        "token",
        "date_joined",
        "last_login",
        "can_invite",
        "quota",
        "invite",
        "preferred_transcription_font",
    ):
        # When either creation or update attempts to pass them through.
        for model, data in [
            (UserCreate, {"username": "User", "email": "user@example.org", key: True}),
            (UserPatch, {key: True}),
        ]:
            # Then they cannot be silently accepted and ignored upstream.
            with pytest.raises(ValidationError):
                _ = model.model_validate(data)


def test_unicode_boundaries_preserve_spelling_and_native_email_validation() -> None:
    # Given native maximum-length values and a Unicode username.
    account = UserCreate.model_validate(
        {
            "username": "Ž" * 150,
            "email": "e" * 255,
            "first_name": "",
            "last_name": "N" * 150,
            "is_active": False,
        }
    )
    # When parsed, then spelling, blanks and explicit false remain exact.
    assert account.username == "Ž" * 150
    assert account.email == "e" * 255
    assert account.first_name == ""
    assert account.is_active is False
    assert (
        UserPatch.model_validate({"email": "Upper@Example.org"}).email
        == "Upper@Example.org"
    )


@pytest.mark.parametrize("search", ["", "  ", "x" * 513, 1, False])
def test_invalid_local_search(search: JsonValue) -> None:
    # Given a value that cannot be a meaningful bounded directory search string.
    # When parsed, then the native list is not queried with an unsupported filter.
    with pytest.raises(ValidationError):
        _ = TypeAdapter[DirectorySearch](DirectorySearch).validate_python(search)


@pytest.mark.parametrize(
    ("tool", "arguments", "extra"),
    [
        ("get_current_user", {}, "password"),
        ("list_users", {"search": "User"}, "groups"),
        ("get_user", {"user_id": 1}, "is_staff"),
        (
            "create_user",
            {"account": {"username": "User", "email": "user@example.org"}},
            "password",
        ),
        (
            "update_user",
            {"user_id": 1, "changes": {"first_name": "Updated"}},
            "is_staff",
        ),
        ("delete_user", {"user_id": 2}, "groups"),
    ],
)
def test_top_level_account_fields_are_rejected_before_network(
    tool: str,
    arguments: dict[str, JsonValue],
    extra: str,
) -> None:
    # Given otherwise-valid account arguments with an unsupported top-level field.
    supplied = dict(arguments)
    supplied[extra] = "unrequested capability"

    async def run(fixture: AccountFixture) -> None:
        async with account_session(fixture) as session:
            discovered = await session.list_tools()
            assert tool in {entry.name for entry in discovered.tools}
            # When a client places a credential/privilege field outside the input model.
            result = await session.call_tool(tool, supplied)
            # Then it cannot be silently discarded while a different operation executes.
            assert result.is_error

    with account_fixture() as fixture:
        fixture.current["is_staff"] = True
        anyio.run(run, fixture)
    assert not fixture.received


@pytest.mark.parametrize("nested", [False, True])
def test_rejected_password_values_are_absent_from_results_and_logs(
    tmp_path: Path, *, nested: bool
) -> None:
    # Given synthetic credential-shaped input that the account API does not support.
    marker = "synthetic-account-value-do-not-echo-8372"
    diagnostic_log = tmp_path / "mcp-stderr.log"
    arguments: dict[str, JsonValue] = (
        {
            "account": {
                "username": "User",
                "email": "user@example.org",
                "password": marker,
            }
        }
        if nested
        else {"password": marker}
    )
    tool = "create_user" if nested else "get_current_user"

    async def run(fixture: AccountFixture) -> None:
        with diagnostic_log.open("w", encoding="utf-8") as stderr:
            async with account_session(fixture, stderr) as session:
                discovered = await session.list_tools()
                assert tool in {entry.name for entry in discovered.tools}
                # When strict argument validation rejects the unsupported password.
                result = await session.call_tool(tool, arguments)
                # Then the error must not echo the rejected credential-shaped value.
                assert result.is_error
                assert marker not in result.model_dump_json()

    with account_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.received
    assert marker not in diagnostic_log.read_text(encoding="utf-8")
