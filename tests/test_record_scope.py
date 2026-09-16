"""Record tag assignments validate the complete effective scope before mutations."""

import anyio
import pytest
from pydantic import JsonValue

from tests.record_fixture import (
    DOCUMENT,
    DOCUMENTS,
    PERSONAL,
    PROJECT,
    PROJECTS,
    RecordFixture,
    record_fixture,
    record_session,
)
from tests.transcription_fixture import invoke


def test_project_assignment_and_clear_use_personal_tags() -> None:
    # Given the current user's personal project-tag definitions.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When assigning one tag during create and clearing during update.
            _ = await invoke(
                session,
                "create_project",
                {
                    "name": "Tagged",
                    "settings": {"tags": [31]},
                },
            )
            _ = await invoke(
                session,
                "update_project",
                {
                    "project_id": 1,
                    "changes": {"tags": []},
                },
            )
            # Then the native full-replacement arrays are kept intact.

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", PERSONAL, None),
        ("POST", PROJECTS, {"name": "Tagged", "tags": [31]}),
        ("GET", PROJECT, None),
        ("GET", PERSONAL, None),
        ("PATCH", PROJECT, {"tags": []}),
    ]


def test_document_tags_follow_effective_project_on_create_move_and_clear() -> None:
    # Given old/new projects with different document-tag catalogues.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When creation and movement target the new project slug.
            _ = await invoke(
                session,
                "create_document",
                {
                    "data": {
                        "name": "Tagged",
                        "project": "new",
                        "main_script": "Latin",
                        "tags": [21],
                    }
                },
            )
            _ = await invoke(
                session,
                "update_document",
                {"document_id": 4, "changes": {"project": "new", "tags": [21]}},
            )
            _ = await invoke(
                session, "update_document", {"document_id": 4, "changes": {"tags": []}}
            )
            # Then empty clears resolve the current project's scope as well.

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    writes = [r for r in fixture.requests if r[0] in {"POST", "PATCH"}]
    assert writes == [
        (
            "POST",
            DOCUMENTS,
            {"name": "Tagged", "project": "new", "main_script": "Latin", "tags": [21]},
        ),
        ("PATCH", DOCUMENT, {"project": "new", "tags": [21]}),
        ("PATCH", DOCUMENT, {"tags": []}),
    ]
    assert [r[1] for r in fixture.requests if r[1].endswith("/tags/")] == [
        PROJECTS + "2/tags/",
        PROJECTS + "2/tags/",
        PROJECT + "tags/",
    ]


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("create_project", {"name": "Wrong", "settings": {"tags": [999]}}),
        ("update_project", {"project_id": 1, "changes": {"tags": [999]}}),
        (
            "create_document",
            {
                "data": {
                    "name": "Wrong",
                    "project": "new",
                    "main_script": "Latin",
                    "tags": [11],
                }
            },
        ),
        (
            "update_document",
            {"document_id": 4, "changes": {"project": "new", "tags": [11]}},
        ),
        ("update_document", {"document_id": 4, "changes": {"tags": [21]}}),
    ],
)
def test_foreign_assigned_tags_never_mutate(
    tool: str, args: dict[str, JsonValue]
) -> None:
    # Given a tag from outside the user's personal/effective document project scope.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When attempting the invalid assignment.
            result = await session.call_tool(tool, args)
            # Then no mutation is sent even if the native serializer would accept it.
            assert result.is_error

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert not [r for r in fixture.requests if r[0] != "GET"]


@pytest.mark.parametrize(
    ("route", "replacement"),
    [
        (DOCUMENT, {"pk": 99, "project_id": 1}),
        (PROJECT, {"id": 99, "slug": "old"}),
        (PROJECT + "tags/", [{"pk": "11"}]),
    ],
)
def test_wrong_identity_or_malformed_tag_catalogue_blocks_write(
    route: str,
    replacement: JsonValue,
) -> None:
    # Given server metadata that cannot prove the target assignment scope.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When existing-project tags are supplied.
            result = await session.call_tool(
                "update_document",
                {
                    "document_id": 4,
                    "changes": {"tags": [11]},
                },
            )
            # Then an unexpected parent or malformed ID never authorizes the write.
            assert result.is_error

    with record_fixture() as fixture:
        fixture.responses[route] = replacement
        anyio.run(run, fixture)
    assert not [r for r in fixture.requests if r[0] != "GET"]


def test_tag_scope_uses_paginated_project_and_tag_catalogues() -> None:
    # Given the target project and tag both occur only on second collection pages.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When a document is created in that project with its visible tag.
            result = await invoke(
                session,
                "create_document",
                {
                    "data": {
                        "name": "Paged",
                        "project": "new",
                        "main_script": "Latin",
                        "tags": [21],
                    }
                },
            )
            # Then complete pagination proves scope and permits the one write.
            assert isinstance(result, dict)

    with record_fixture() as fixture:
        fixture.responses[PROJECTS] = {
            "count": 2,
            "results": [fixture.project],
            "next": PROJECTS + "?page=2",
        }
        fixture.responses[PROJECTS + "?page=2"] = {
            "count": 2,
            "next": None,
            "results": [{"id": 2, "slug": "new", "name": "New"}],
        }
        fixture.responses[PROJECTS + "2/tags/"] = {
            "count": 1,
            "results": [],
            "next": PROJECTS + "2/tags/?page=2",
        }
        fixture.responses[PROJECTS + "2/tags/?page=2"] = {
            "count": 1,
            "next": None,
            "results": [{"pk": 21}],
        }
        anyio.run(run, fixture)
    assert len([r for r in fixture.requests if r[0] == "POST"]) == 1
    assert ("GET", PROJECTS + "?page=2", None) in fixture.requests
    assert ("GET", PROJECTS + "2/tags/?page=2", None) in fixture.requests


def test_inaccessible_assignment_scope_stops_before_mutation() -> None:
    # Given permission denial while reading the effective project's tag definitions.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When the caller attempts a document assignment in that project.
            result = await session.call_tool(
                "update_document",
                {
                    "document_id": 4,
                    "changes": {"tags": [11]},
                },
            )
            # Then the permission error propagates without attempting a PATCH.
            assert result.is_error

    with record_fixture() as fixture:
        fixture.failures[PROJECT + "tags/"] = 403
        anyio.run(run, fixture)
    assert not [r for r in fixture.requests if r[0] != "GET"]
