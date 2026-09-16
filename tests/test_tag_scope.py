"""Parent and tag identities are verified before any definition mutation."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.tag_fixture import PERSONAL, PROJECT, PROJECT_TAGS, tag_fixture, tag_session

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize("tool", ["create_tag", "update_tag", "delete_tag"])
@pytest.mark.parametrize("failure", ["wrong_id", "forbidden", "missing"])
def test_parent_scope_failure_sends_no_mutation(tool: str, failure: str) -> None:
    with tag_fixture() as fixture:
        if failure == "wrong_id":
            fixture.project["id"] = 8
        else:
            fixture.failures[PROJECT] = 403 if failure == "forbidden" else 404

        async def run() -> None:
            async with tag_session(fixture) as session:
                args: dict[str, JsonValue] = {
                    "target": {"scope": "project_documents", "project_id": 7}
                }
                if tool == "create_tag":
                    args["data"] = {"name": "New"}
                if tool != "create_tag":
                    args["tag_id"] = 2
                if tool == "update_tag":
                    args["changes"] = {"name": "New"}
                response = await session.call_tool(tool, args)
                assert response.is_error

        anyio.run(run)
    assert fixture.requests == [("GET", PROJECT, None)]


@pytest.mark.parametrize("personal", [False, True])
@pytest.mark.parametrize("tool", ["get_tag", "update_tag", "delete_tag"])
def test_wrong_tag_identity_is_rejected(*, personal: bool, tool: str) -> None:
    target: dict[str, JsonValue] = (
        {"scope": "personal_projects"}
        if personal
        else {"scope": "project_documents", "project_id": 7}
    )
    base = PERSONAL if personal else PROJECT_TAGS
    with tag_fixture() as fixture:
        fixture.tag["pk"] = 3

        async def run() -> None:
            async with tag_session(fixture) as session:
                args: dict[str, JsonValue] = {"target": target, "tag_id": 2}
                if tool == "update_tag":
                    args["changes"] = {"color": "red"}
                response = await session.call_tool(tool, args)
                assert response.is_error

        anyio.run(run)
    expected = [] if personal else [("GET", PROJECT, None)]
    assert fixture.requests == [*expected, ("GET", base + "2/", None)]


@pytest.mark.parametrize("status", [403, 404])
def test_inaccessible_tag_sends_no_patch(status: int) -> None:
    with tag_fixture() as fixture:
        fixture.failures[PROJECT_TAGS + "2/"] = status

        async def run() -> None:
            async with tag_session(fixture) as session:
                response = await session.call_tool(
                    "update_tag",
                    {
                        "target": {"scope": "project_documents", "project_id": 7},
                        "tag_id": 2,
                        "changes": {"color": "red"},
                    },
                )
                assert response.is_error

        anyio.run(run)
    assert fixture.requests == [
        ("GET", PROJECT, None),
        ("GET", PROJECT_TAGS + "2/", None),
    ]


def test_malformed_public_scopes_and_identifiers_never_reach_api() -> None:
    with tag_fixture() as fixture:

        async def run() -> None:
            async with tag_session(fixture) as session:
                invalid: list[dict[str, JsonValue]] = [
                    {
                        "target": {"scope": "project_documents", "project_id": True},
                        "tag_id": 2,
                    },
                    {
                        "target": {"scope": "personal_projects", "project_id": 7},
                        "tag_id": 2,
                    },
                    {"target": {"scope": "personal_projects"}, "tag_id": 0},
                    {"target": {"scope": "personal_projects"}, "tag_id": "2"},
                ]
                for args in invalid:
                    response = await session.call_tool("get_tag", args)
                    assert response.is_error

        anyio.run(run)
    assert not fixture.requests
