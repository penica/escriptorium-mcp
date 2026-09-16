"""Sharing targets reject ambiguous selectors and unsupported permission fields."""

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.sharing_models import ShareTarget


@pytest.mark.parametrize(
    "target",
    [
        {},
        {"kind": "other"},
        {"kind": "user"},
        {"kind": "group"},
        {"kind": "user", "username": None},
        {"kind": "user", "username": ""},
        {"kind": "user", "username": "   "},
        {"kind": "user", "username": 7},
        {"kind": "user", "username": "x" * 151},
        {"kind": "user", "username": "member", "group_id": 2},
        {"kind": "group", "group_id": 2, "username": "member"},
        {"kind": "group", "group_id": 0},
        {"kind": "group", "group_id": -1},
        {"kind": "group", "group_id": "2"},
        {"kind": "group", "group_id": True},
        {"kind": "group", "group_id": None},
        {"kind": "user", "username": "member", "role": "owner"},
        {"kind": "user", "username": "member", "remove": True},
        {"kind": "group", "group_id": 2, "replace": True},
        {"kind": "group", "group_id": 2, "expires_at": "2026-10-01"},
    ],
)
def test_invalid_sharing_target(target: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        _ = TypeAdapter[ShareTarget](ShareTarget).validate_python(target)


@pytest.mark.parametrize("username", ["Maša.Test+1", "x" * 150])
def test_username_is_preserved_without_normalizing(username: str) -> None:
    value = TypeAdapter[ShareTarget](ShareTarget).validate_python(
        {"kind": "user", "username": username}
    )
    assert value.model_dump() == {"kind": "user", "username": username}
