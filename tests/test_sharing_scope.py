"""Only the requested resource and visible member group may be shared."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.sharing_fixture import (
    DOCUMENT,
    GROUP,
    PROJECT,
    sharing_fixture,
    sharing_session,
)

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize("resource", ["project", "document"])
@pytest.mark.parametrize("failure", ["wrong_identity", "denied", "missing"])
def test_resource_scope_failure_prevents_post(resource: str, failure: str) -> None:
    route = PROJECT if resource == "project" else DOCUMENT
    identifier = 7 if resource == "project" else 4
    with sharing_fixture() as fixture:
        record = fixture.project if resource == "project" else fixture.document
        if failure == "wrong_identity":
            record["id" if resource == "project" else "pk"] = 999
        else:
            fixture.failures[route] = 403 if failure == "denied" else 404

        async def run() -> None:
            async with sharing_session(fixture) as session:
                response = await session.call_tool(
                    "share_" + resource,
                    {
                        resource + "_id": identifier,
                        "target": {"kind": "group", "group_id": 2},
                    },
                )
                assert response.is_error

        anyio.run(run)
    assert fixture.requests == [("GET", route, None)]


@pytest.mark.parametrize("resource", ["project", "document"])
@pytest.mark.parametrize("failure", ["wrong_identity", "denied", "missing"])
def test_group_membership_scope_failure_prevents_post(
    resource: str, failure: str
) -> None:
    route = PROJECT if resource == "project" else DOCUMENT
    identifier = 7 if resource == "project" else 4
    with sharing_fixture() as fixture:
        if failure == "wrong_identity":
            fixture.group["pk"] = 99
        else:
            fixture.failures[GROUP] = 403 if failure == "denied" else 404

        async def run() -> None:
            async with sharing_session(fixture) as session:
                response = await session.call_tool(
                    "share_" + resource,
                    {
                        resource + "_id": identifier,
                        "target": {"kind": "group", "group_id": 2},
                    },
                )
                assert response.is_error

        anyio.run(run)
    assert fixture.requests == [("GET", route, None), ("GET", GROUP, None)]


def test_invalid_public_ids_and_targets_make_no_requests() -> None:
    with sharing_fixture() as fixture:

        async def run() -> None:
            async with sharing_session(fixture) as session:
                invalid: list[dict[str, JsonValue]] = [
                    {"project_id": True, "target": {"kind": "group", "group_id": 2}},
                    {"project_id": 7, "target": {"kind": "group", "group_id": "2"}},
                    {
                        "project_id": 7,
                        "target": {"kind": "user", "username": "member", "group_id": 2},
                    },
                    {
                        "project_id": 7,
                        "target": {
                            "kind": "user",
                            "username": "member",
                            "remove": True,
                        },
                    },
                    {
                        "project_id": 7,
                        "target": {"kind": "user", "username": "member"},
                        "replace": True,
                    },
                ]
                for args in invalid:
                    response = await session.call_tool("share_project", args)
                    assert response.is_error

        anyio.run(run)
    assert not fixture.requests


@pytest.mark.parametrize("resource", ["project", "document"])
def test_unsupported_top_level_permission_modes_never_grant(resource: str) -> None:
    with sharing_fixture() as fixture:

        async def run() -> None:
            async with sharing_session(fixture) as session:
                catalog = await session.list_tools()
                tool = next(
                    item for item in catalog.tools if item.name == "share_" + resource
                )
                assert tool.input_schema.get("additionalProperties") is False
                for flag in ("replace", "remove", "role", "expires_at"):
                    response = await session.call_tool(
                        "share_" + resource,
                        {
                            resource + "_id": 7 if resource == "project" else 4,
                            "target": {"kind": "user", "username": "member"},
                            flag: True,
                        },
                    )
                    assert response.is_error

        anyio.run(run)
    assert not fixture.requests
