"""Sharing over authenticated HTTP preserves native expanded responses."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.sharing_fixture import DOCUMENT, GROUP, PROJECT, sharing_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_sharing() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        rejected = await session.call_tool(
            "share_document",
            {
                "document_id": 4,
                "target": {"kind": "user", "username": "member"},
                "remove": True,
            },
        )
        assert rejected.is_error
        project = decoded_result(
            await session.call_tool(
                "share_project",
                {"project_id": 7, "target": {"kind": "user", "username": "New.User"}},
            )
        )
        assert isinstance(project, dict)
        assert project["id"] == 7
        users = project["shared_with_users"]
        assert isinstance(users, list)
        assert len(users) == 2
        document = decoded_result(
            await session.call_tool(
                "share_document",
                {"document_id": 4, "target": {"kind": "group", "group_id": 2}},
            )
        )
        assert isinstance(document, dict)
        assert document["pk"] == 4
        groups = document["shared_with_groups"]
        assert isinstance(groups, list)
        assert len(groups) == 2


def test_sharing_through_authenticated_http(monkeypatch: pytest.MonkeyPatch) -> None:
    with sharing_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_sharing)
    assert fixture.requests == [
        ("GET", PROJECT, None),
        ("POST", PROJECT + "share/", {"user": "New.User"}),
        ("GET", DOCUMENT, None),
        ("GET", GROUP, None),
        ("POST", DOCUMENT + "share/", {"group": 2}),
    ]
