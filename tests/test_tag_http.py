"""Tag definition CRUD through authenticated Streamable HTTP MCP."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.tag_fixture import PROJECT_TAGS, tag_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_tags() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        target = {"scope": "project_documents", "project_id": 7}
        created = decoded_result(
            await session.call_tool(
                "create_tag",
                {"target": target, "data": {"name": "New", "color": "red"}},
            )
        )
        assert isinstance(created, dict)
        assert created["pk"] == 2
        updated = decoded_result(
            await session.call_tool(
                "update_tag",
                {"target": target, "tag_id": 2, "changes": {"name": "Reviewed"}},
            )
        )
        assert isinstance(updated, dict)
        assert updated["name"] == "Reviewed"
        assert updated["color"] == "red"
        read = decoded_result(
            await session.call_tool("get_tag", {"target": target, "tag_id": 2})
        )
        assert read == updated
        listed = decoded_result(
            await session.call_tool("list_tags", {"target": target})
        )
        assert isinstance(listed, dict)
        assert listed["results"] == [updated]
        deleted = decoded_result(
            await session.call_tool("delete_tag", {"target": target, "tag_id": 2})
        )
        assert deleted == {"status": "success", "http_status": 204}


def test_tag_lifecycle_over_authenticated_http(monkeypatch: pytest.MonkeyPatch) -> None:
    with tag_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_tags)
    mutations = [row for row in fixture.requests if row[0] != "GET"]
    assert mutations == [
        ("POST", PROJECT_TAGS, {"name": "New", "color": "red"}),
        ("PATCH", PROJECT_TAGS + "2/", {"name": "Reviewed"}),
        ("DELETE", PROJECT_TAGS + "2/", {}),
    ]
