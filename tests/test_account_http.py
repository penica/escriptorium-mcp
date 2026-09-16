"""Self-service account updates over authenticated Streamable HTTP."""

import anyio
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.account_fixture import SELF, AccountFixture, account_fixture
from tests.test_http import authenticated_client, running_endpoint
from tests.transcription_fixture import decoded_result


async def exercise_http(fixture: AccountFixture) -> None:
    async with (
        running_endpoint() as endpoint,
        authenticated_client() as http,
        Client(streamable_http_client(endpoint, http_client=http)) as session,
    ):
        # When a nonstaff user reads and updates their own allowed account fields.
        read = await session.call_tool("get_user", {"user_id": 1})
        assert decoded_result(read) == fixture.current
        result = await session.call_tool(
            "update_user",
            {
                "user_id": 1,
                "changes": {"email": "new@example.org", "first_name": ""},
            },
        )
        # Then the same raw success and explicit clearing are exposed over HTTP.
        assert decoded_result(result) == {
            "pk": 1,
            "saved": {"email": "new@example.org", "first_name": ""},
        }


def test_authenticated_account_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a bearer-authenticated MCP service and an isolated account backend.
    with account_fixture() as fixture:
        monkeypatch.setenv("ESCRIPTORIUM_URL", fixture.url)
        monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "fixture-key")
        anyio.run(exercise_http, fixture)
    assert fixture.requests == [
        ("GET", SELF, None),
        ("GET", SELF, None),
        ("PATCH", SELF, {"email": "new@example.org", "first_name": ""}),
    ]
