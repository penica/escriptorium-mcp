"""Native project/document setting writes retain omission and assignment semantics."""

from typing import TYPE_CHECKING

import anyio

from tests.record_fixture import (
    DOCUMENT,
    DOCUMENTS,
    PROJECT,
    PROJECTS,
    RecordFixture,
    record_fixture,
    record_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_project_guidelines_clear() -> None:
    # Given a project with a nullable native guidelines setting.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When the new settings tool clears that setting.
            result = await invoke(
                session,
                "update_project",
                {
                    "project_id": 1,
                    "changes": {"guidelines": None},
                },
            )
            # Then the explicit null survives the wire rather than being omitted.
            assert result == {"saved": {"guidelines": None}}

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("PATCH", PROJECT, {"guidelines": None})]


def test_create_project_settings_omit_defaults_and_preserve_blank() -> None:
    # Given callers using original name-only arguments or optional settings.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When omitted, null and empty settings are supplied.
            variants: list[dict[str, JsonValue]] = [
                {"name": "Name"},
                {"name": "Name", "settings": None},
                {"name": "Name", "settings": {}},
                {"name": "Name", "settings": {"guidelines": ""}},
            ]
            for args in variants:
                result = await invoke(session, "create_project", args)
                # Then the native request body has no synthetic sharing/defaults.
                assert isinstance(result, dict)

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("POST", PROJECTS, {"name": "Name"}),
        ("POST", PROJECTS, {"name": "Name"}),
        ("POST", PROJECTS, {"name": "Name"}),
        ("POST", PROJECTS, {"name": "Name", "guidelines": ""}),
    ]


def test_record_names_accept_512_across_existing_and_new_writes() -> None:
    # Given a native maximum-length display name.
    name = "N" * 512

    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When all record-name mutation surfaces receive that valid value.
            variants: list[tuple[str, dict[str, JsonValue]]] = [
                ("create_project", {"name": name}),
                ("rename_project", {"project_id": 1, "name": name}),
                ("update_project", {"project_id": 1, "changes": {"name": name}}),
                (
                    "create_document",
                    {"data": {"name": name, "project": "old", "main_script": "Latin"}},
                ),
                ("update_document", {"document_id": 4, "changes": {"name": name}}),
            ]
            for tool, args in variants:
                result = await invoke(session, tool, args)
                # Then the accepted raw response contains the submitted name.
                assert isinstance(result, dict)
                saved = result["saved"]
                assert isinstance(saved, dict)
                assert saved["name"] == name

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert all(r[0] in {"POST", "PATCH"} for r in fixture.requests)
    assert fixture.requests[3][2] == {
        "name": name,
        "project": "old",
        "main_script": "Latin",
    }


def test_document_confidence_false_and_move_without_tags_remain_single_writes() -> None:
    # Given an existing caller moving by project slug with omitted tags.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When false is explicit and tag assignments are not supplied.
            _ = await invoke(
                session,
                "update_document",
                {
                    "document_id": 4,
                    "changes": {"project": "new", "show_confidence_viz": False},
                },
            )
            _ = await invoke(
                session,
                "create_document",
                {
                    "data": {
                        "name": "New",
                        "project": "new",
                        "main_script": "Latin",
                        "show_confidence_viz": False,
                    }
                },
            )
            # Then read_direction, line_offset and tags retain native omission.

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("PATCH", DOCUMENT, {"project": "new", "show_confidence_viz": False}),
        (
            "POST",
            DOCUMENTS,
            {
                "name": "New",
                "project": "new",
                "main_script": "Latin",
                "show_confidence_viz": False,
            },
        ),
    ]


def test_project_name_limits_are_enforced_on_registry_and_rename_tools() -> None:
    # Given a name longer than the native record limit on both public entry points.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When the registry create tool or existing rename tool receives 513 chars.
            created = await session.call_tool("create_project", {"name": "N" * 513})
            renamed = await session.call_tool(
                "rename_project",
                {
                    "project_id": 1,
                    "name": "N" * 513,
                },
            )
            # Then validation runs before either tool can reach the API.
            assert created.is_error
            assert renamed.is_error

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
