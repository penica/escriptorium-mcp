"""Additive sharing returns native expanded grants without extra discovery."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.sharing_fixture import (
    DOCUMENT,
    GROUP,
    PROJECT,
    SharingFixture,
    sharing_fixture,
    sharing_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_project_username_share_is_additive() -> None:
    async def run(fixture: SharingFixture) -> None:
        async with sharing_session(fixture) as session:
            result = await invoke(
                session,
                "share_project",
                {"project_id": 7, "target": {"kind": "user", "username": "New.User"}},
            )
            assert result == fixture.project
            grants = fixture.project["shared_with_users"]
            assert isinstance(grants, list)
            assert len(grants) == 2

    with sharing_fixture() as fixture:
        anyio.run(run, fixture)


@pytest.mark.parametrize("resource", ["project", "document"])
@pytest.mark.parametrize("kind", ["user", "group"])
def test_native_grants_are_additive_for_both_scopes(resource: str, kind: str) -> None:
    route = PROJECT if resource == "project" else DOCUMENT
    identifier = 7 if resource == "project" else 4
    target: dict[str, JsonValue] = (
        {"kind": "user", "username": "Maša.Test+1"}
        if kind == "user"
        else {"kind": "group", "group_id": 2}
    )
    body: dict[str, JsonValue] = (
        {"user": "Maša.Test+1"} if kind == "user" else {"group": 2}
    )
    with sharing_fixture() as fixture:
        original = fixture.project if resource == "project" else fixture.document

        async def run() -> None:
            async with sharing_session(fixture) as session:
                result = await invoke(
                    session,
                    "share_" + resource,
                    {resource + "_id": identifier, "target": target},
                )
                assert result == original
                users, groups = (
                    original["shared_with_users"],
                    original["shared_with_groups"],
                )
                assert isinstance(users, list)
                assert isinstance(groups, list)
                assert len(users) == (2 if kind == "user" else 1)
                assert len(groups) == (2 if kind == "group" else 1)
                assert isinstance(users[0], dict)
                assert users[0]["pk"] == 3
                assert isinstance(groups[0], dict)
                assert groups[0]["pk"] == 5

        anyio.run(run)
    expected = [("GET", route, None)]
    if kind == "group":
        expected.append(("GET", GROUP, None))
    assert fixture.requests == [*expected, ("POST", route + "share/", body)]


@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_native_sharing_failure_is_not_retried(status: int) -> None:
    with sharing_fixture() as fixture:
        fixture.failures[PROJECT + "share/"] = status

        async def run() -> None:
            async with sharing_session(fixture) as session:
                response = await session.call_tool(
                    "share_project",
                    {"project_id": 7, "target": {"kind": "user", "username": "member"}},
                )
                assert response.is_error
                assert str(status) in str(response.content)
                assert "fixture-key" not in str(response.content)

        anyio.run(run)
    assert fixture.requests == [
        ("GET", PROJECT, None),
        ("POST", PROJECT + "share/", {"user": "member"}),
    ]


def test_lost_success_response_does_not_repeat_grant() -> None:
    with sharing_fixture() as fixture:
        fixture.disconnect.add(DOCUMENT + "share/")

        async def run() -> None:
            async with sharing_session(fixture) as session:
                response = await session.call_tool(
                    "share_document",
                    {"document_id": 4, "target": {"kind": "group", "group_id": 2}},
                )
                assert response.is_error

        anyio.run(run)
    assert fixture.requests == [
        ("GET", DOCUMENT, None),
        ("GET", GROUP, None),
        ("POST", DOCUMENT + "share/", {"group": 2}),
    ]
    grants = fixture.document["shared_with_groups"]
    assert isinstance(grants, list)
    assert len(grants) == 2
