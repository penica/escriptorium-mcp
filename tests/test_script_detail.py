import anyio
import pytest
from pydantic import JsonValue

from tests.record_fixture import RecordFixture, record_fixture, record_session
from tests.transcription_fixture import invoke

SCRIPTS = "/api/scripts/"
SCRIPT = SCRIPTS + "7/"
MISSING_SCRIPT = SCRIPTS + "999/"


def test_script_detail_discovery_and_read_preserve_list_behavior() -> None:
    # Given a native script catalogue and sparse detail record with future fields.
    script: JsonValue = {
        "id": 7,
        "name": "Latin",
        "direction": "horizontal-lr",
        "future": {"nullable": None, "zero": 0},
    }
    catalogue: JsonValue = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [script],
    }

    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When actual MCP discovery precedes both the existing list and detail read.
            discovered = await session.list_tools()
            tools = {tool.name: tool for tool in discovered.tools}
            detail = tools["get_script"]
            assert detail.annotations is not None
            assert detail.annotations.read_only_hint is True
            assert detail.input_schema["properties"] == {
                "script_id": {
                    "exclusiveMinimum": 0,
                    "title": "Script Id",
                    "type": "integer",
                }
            }
            assert await invoke(session, "list_scripts", {}) == catalogue
            result = await invoke(session, "get_script", {"script_id": 7})
            # Then both native response shapes and detail fields remain unmodified.
            assert result == script

    with record_fixture() as fixture:
        fixture.responses[SCRIPTS] = catalogue
        fixture.responses[SCRIPT] = script
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", SCRIPTS, None), ("GET", SCRIPT, None)]


@pytest.mark.parametrize("script_id", [0, -1, True, "7", None, 7.5])
def test_script_detail_rejects_invalid_ids_without_request(
    script_id: JsonValue,
) -> None:
    # Given a value that is not an exact positive script primary key.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When it crosses the real MCP STDIO validation boundary.
            response = await session.call_tool("get_script", {"script_id": script_id})
            # Then it cannot become an authenticated API route.
            assert response.is_error

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == []


@pytest.mark.parametrize(("route", "status"), [(MISSING_SCRIPT, 404), (SCRIPT, 403)])
def test_script_detail_preserves_missing_and_denied_errors(
    route: str, status: int
) -> None:
    # Given an absent or inaccessible native script record.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When its valid identity reaches the native detail endpoint.
            response = await session.call_tool(
                "get_script", {"script_id": 999 if status == 404 else 7}
            )
            # Then the access error is not fabricated into a script record.
            assert response.is_error

    with record_fixture() as fixture:
        fixture.failures[route] = status
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", route, None)]
