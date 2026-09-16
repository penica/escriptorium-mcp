"""Font discovery exposes only typed read inputs and rejects unsupported actions."""

import anyio
import pytest
from pydantic import JsonValue

from tests.font_fixture import FontFixture, font_fixture, font_session


@pytest.mark.parametrize("font_id", [0, -1, True, "3", None, 3.5])
def test_invalid_font_id_never_requests_api(font_id: JsonValue) -> None:
    # Given an input that is not an exact positive integer font primary key.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the real MCP tool validates its public argument.
            result = await session.call_tool("get_font", {"font_id": font_id})
            # Then malformed identity cannot become an authenticated route.
            assert result.is_error

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.received


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("list_fonts", {"url": "https://foreign.invalid/font.woff2"}),
        ("get_font", {"font_id": 3, "download": True}),
    ],
)
def test_unknown_font_arguments_are_rejected_before_network(
    tool: str, arguments: dict[str, JsonValue]
) -> None:
    # Given a purported download option on a catalogue-only API tool.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            tools = await session.list_tools()
            assert tool in {entry.name for entry in tools.tools}
            # When unknown top-level fields are supplied to the strict tool.
            result = await session.call_tool(tool, arguments)
            # Then they are rejected instead of ignored or interpreted as file actions.
            assert result.is_error

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.received


def test_font_catalogue_schema_is_read_only_and_has_no_mutation_surface() -> None:
    # Given the actual MCP discovery catalogue.
    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When tools and their advertised argument contracts are discovered.
            discovered = await session.list_tools()
            tools = {entry.name: entry for entry in discovered.tools}
            # Then only native catalogue reads are offered for font administration.
            assert {"list_fonts", "get_font"}.issubset(tools)
            assert (
                not {"upload_font", "create_font", "update_font", "delete_font"}
                & tools.keys()
            )
            for name in ("list_fonts", "get_font"):
                tool = tools[name]
                assert tool.annotations is not None
                assert tool.annotations.read_only_hint is True
                assert tool.input_schema["additionalProperties"] is False

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.received
