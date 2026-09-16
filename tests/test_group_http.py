"""Native group creation verification over authenticated Streamable HTTP."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.group_fixture import CURRENT, GROUP, GROUPS, group_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def create_group_over_http() -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When acknowledged creation crosses authenticated HTTP MCP.
        response = await session.call_tool(
            "create_group",
            {"name": "Researchers", "acknowledge_native_create_limitations": True},
        )
        # Then the source-like inaccessible group is accepted but not verified usable.
        result = decoded_result(response)
        assert isinstance(result, dict)
        assert result["accepted"] is True
        verification = result["verification"]
        assert isinstance(verification, dict)
        assert verification["status"] == "unavailable"
        assert verification["creator_is_member"] is None
        assert verification["creator_is_owner"] is None


def test_orphan_group_acceptance_over_authenticated_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a deployment whose REST create omits creator membership.
    with group_fixture() as fixture:
        fixture.created[0] = {"pk": 7, "users": [], "owner": None}
        fixture.failures["GET " + GROUP] = 404
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(create_group_over_http)
    assert fixture.requests == [
        ("GET", CURRENT, None),
        ("POST", GROUPS, {"name": "Researchers"}),
        ("GET", GROUP, None),
    ]
