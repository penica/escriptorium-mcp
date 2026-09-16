"""Read and layer-setting contracts through real MCP and API transports."""

from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from mcp_types import TextContent
from pydantic import JsonValue

from tests.transcription_fixture import (
    LAYER,
    TEXTS,
    TranscriptionFixture,
    invoke,
    transcription_fixture,
    transcription_session,
)


@pytest.mark.parametrize("ordering", ["frequency", "-frequency", "char", "-char"])
def test_statistics_preserve_zero_unicode_and_server_shape(ordering: str) -> None:
    # Given raw statistics containing zero counts and Unicode characters.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When selecting an ordering.
            result = await invoke(
                session,
                "get_transcription_statistics",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "ordering": ordering,
                },
            )
            # Then no derived or normalized counts replace the upstream values.
            assert result == fixture.stats

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[0] == ("GET", LAYER, None)
    assert parse_qs(urlsplit(fixture.requests[-1][1]).query) == {"ordering": [ordering]}


def test_character_lookup_encodes_one_unicode_codepoint() -> None:
    # Given a newer backend exposing character lookup.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When a Unicode character is requested.
            result = await invoke(
                session,
                "find_transcription_pages_by_character",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "character": "č",
                },
            )
            # Then its raw page results preserve zero frequency.
            assert result == {"parts": [{"document_part_id": 10, "frequency": 0}]}

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[0] == ("GET", LAYER, None)
    assert parse_qs(urlsplit(fixture.requests[-1][1]).query) == {"char": ["č"]}


@pytest.mark.parametrize("status", [403, 404])
def test_lookup_failure_is_not_success_or_assumed_version(status: int) -> None:
    # Given an existing layer whose lookup endpoint denies access or is hidden.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When lookup is attempted after parent verification.
            result = await session.call_tool(
                "find_transcription_pages_by_character",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "character": "a",
                },
            )
            # Then a genuine tool error preserves the distinction from empty results.
            assert result.is_error
            block = result.content[0]
            assert isinstance(block, TextContent)
            if status == 404:
                assert any(
                    word in block.text.lower() for word in ("unavailable", "hidden")
                )
            else:
                assert "403" in block.text

    with transcription_fixture() as fixture:
        fixture.failures[LAYER + "parts_by_char/"] = status
        anyio.run(run, fixture)
    assert fixture.requests[0] == ("GET", LAYER, None)
    assert len(fixture.requests) == 2


def test_missing_parent_prevents_capability_probe() -> None:
    # Given a layer the caller cannot access.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When lookup is requested.
            result = await session.call_tool(
                "find_transcription_pages_by_character",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "character": "a",
                },
            )
            # Then the missing layer is reported before probing feature support.
            assert result.is_error

    with transcription_fixture() as fixture:
        fixture.failures[LAYER] = 404
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", LAYER, None)]


@pytest.mark.parametrize("character", ["", "ab", "a\u0301"])
def test_character_lookup_rejects_non_single_codepoint(character: str) -> None:
    # Given an empty string or multi-codepoint sequence.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When it crosses the public boundary.
            result = await session.call_tool(
                "find_transcription_pages_by_character",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "character": character,
                },
            )
            # Then validation fails without probing the server.
            assert result.is_error

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize(
    ("tool", "args", "route"),
    [
        ("get_transcription", {"document_id": 4, "transcription_id": 2}, LAYER),
        (
            "get_line_transcription",
            {"target": {"document_id": 4, "page_id": 10, "line_transcription_id": 91}},
            TEXTS + "91/",
        ),
    ],
)
def test_individual_reads_preserve_raw_metadata(
    tool: str, args: dict[str, JsonValue], route: str
) -> None:
    # Given a stored layer or line with nullable metadata and history.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When requested individually.
            result = await invoke(session, tool, args)
            # Then the full server record survives unchanged.
            assert result == (
                fixture.layer if tool == "get_transcription" else fixture.records[0]
            )

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("GET", route, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "č" * 512},
        {"archived": True},
        {"comments": None, "avg_confidence": None},
        {"comments": "", "avg_confidence": 0.0},
    ],
)
def test_layer_patch_preserves_omitted_nullable_fields(
    changes: dict[str, JsonValue],
) -> None:
    # Given a writable layer and a partial update.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When applying exactly the supplied fields.
            result = await invoke(
                session,
                "update_transcription",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "changes": changes,
                },
            )
            # Then the stored server record is returned.
            assert result == fixture.layer

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("PATCH", LAYER, changes)


def test_page_list_forwards_optional_layer_filter() -> None:
    # Given a page with transcriptions.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When selecting a layer in the page listing.
            result = await invoke(
                session,
                "get_page_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "transcription_id": 2,
                },
            )
            # Then the existing records retain their raw metadata.
            assert result == fixture.records

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert parse_qs(urlsplit(fixture.requests[-1][1]).query) == {"transcription": ["2"]}


@pytest.mark.parametrize(
    "changes", [{}, {"name": ""}, {"name": "x" * 513}, {"archived": None}]
)
def test_invalid_layer_patch_fails_before_network(
    changes: dict[str, JsonValue],
) -> None:
    # Given empty or serializer-incompatible layer settings.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When settings cross the public boundary.
            result = await session.call_tool(
                "update_transcription",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                    "changes": changes,
                },
            )
            # Then validation rejects them before upstream access.
            assert result.is_error

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize("count", [0, 1, 2])
def test_page_list_retains_empty_single_and_multiple_result_arrays(count: int) -> None:
    # Given zero, one or two stored records.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When the complete page result is returned through MCP.
            result = await invoke(
                session,
                "get_page_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "transcription_id": 2,
                },
            )
            # Then the array and every record survive SDK text-block flattening.
            assert isinstance(result, list)
            assert result == fixture.records
            assert len(result) == count

    with transcription_fixture() as fixture:
        del fixture.records[count:]
        anyio.run(run, fixture)
