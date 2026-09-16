"""Strict group input boundaries reject unsupported consent and membership writes."""

import anyio
import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.group_models import GroupName
from tests.group_fixture import GroupFixture, group_fixture, group_session


@pytest.mark.parametrize("name", ["", " ", "x" * 151, None, 123])
def test_group_name_rejects_invalid_native_bounds(name: JsonValue) -> None:
    # Given a blank, overlong or non-string name.
    # When parsed, then a native group name cannot be formed.
    with pytest.raises(ValidationError):
        _ = TypeAdapter[str](GroupName).validate_python(name)


def test_group_name_accepts_maximum_unicode_length() -> None:
    # Given the maximum supported name length with spaces and Unicode.
    name = "Č" * 148 + " a"
    # When parsed, then spelling and whitespace are retained.
    assert TypeAdapter[str](GroupName).validate_python(name) == name


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"acknowledge_native_create_limitations": False},
        {"acknowledge_native_create_limitations": None},
        {"acknowledge_native_create_limitations": 1},
        {"acknowledge_native_create_limitations": "true"},
        {"acknowledge_native_create_limitations": True, "owner": 2},
        {"acknowledge_native_create_limitations": True, "users": [2]},
    ],
)
def test_invalid_create_acknowledgment_or_readonly_fields_perform_no_io(
    extra: dict[str, JsonValue],
) -> None:
    # Given missing/coercible consent or an attempted membership/owner assignment.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When the public tool input is validated.
            result = await session.call_tool(
                "create_group", {"name": "Researchers", **extra}
            )
            # Then no current-account read or native write takes place.
            assert result.is_error

    with group_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


def test_group_catalogue_rejects_unknown_arguments_in_all_five_schemas() -> None:
    # Given the five public group tools exposed through an actual MCP subprocess.
    async def run(fixture: GroupFixture) -> None:
        async with group_session(fixture) as session:
            # When a client discovers their input schemas.
            catalogue = await session.list_tools()
            expected = {
                "list_groups",
                "get_group",
                "create_group",
                "update_group",
                "delete_group",
            }
            schemas = {
                tool.name: tool.input_schema
                for tool in catalogue.tools
                if tool.name in expected
            }
            # Then every tool forbids unsupported top-level fields.
            assert set(schemas) == expected
            assert all(
                schema.get("additionalProperties") is False
                for schema in schemas.values()
            )

    with group_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
