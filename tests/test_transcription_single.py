"""Single-record graph edits and scoped link changes through actual STDIO MCP."""

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


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"graphs": [{"c": "č", "confidence": 0.0}], "avg_confidence": 0.0},
        {"graphs": None, "avg_confidence": None},
    ],
)
def test_single_create_preserves_supplied_fields_and_omissions(
    extra: dict[str, JsonValue],
) -> None:
    # Given new text with optional graph fields deliberately supplied or omitted.
    text: dict[str, JsonValue] = {
        "line": 12,
        "transcription": 3,
        "content": "č",
        **extra,
    }

    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When the existing single-create tool is called.
            result = await invoke(
                session,
                "create_line_transcription",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "text": text,
                },
            )
            # Then it returns the complete created row with no invented fields.
            assert result == {"pk": 93, **text}

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", TEXTS, text)]


@pytest.mark.parametrize(
    "changes",
    [
        {"content": ""},
        {"graphs": [dict[str, JsonValue]()]},
        {"graphs": None, "avg_confidence": None},
        {"graphs": [{"poly": [[0, 0], [2, 0], [1, 2]], "confidence": 1.0}]},
    ],
)
def test_single_patch_preserves_graphs_nulls_and_existing_content_behavior(
    changes: dict[str, JsonValue],
) -> None:
    # Given an existing row with metadata and historical text.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When a content or graph-only patch is supplied without link changes.
            result = await invoke(
                session,
                "update_line_transcription",
                {
                    "target": {
                        "document_id": 4,
                        "page_id": 10,
                        "line_transcription_id": 91,
                    },
                    "changes": changes,
                },
            )
            # Then the response retains every other record field and its history.
            assert result == fixture.records[0]
            assert isinstance(result, dict)
            assert result["versions"] == [{"content": "history"}]
            assert all(result[key] == value for key, value in changes.items())

    with transcription_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("PATCH", TEXTS + "91/", changes)]


@pytest.mark.parametrize("changes", [{"line": 99}, {"transcription": 99}, {"line": 12}])
def test_single_link_change_rejects_foreign_ids_or_existing_pair(
    changes: dict[str, JsonValue],
) -> None:
    # Given foreign IDs or a pair already occupied by another row.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When attempting to redirect the record to that identity.
            result = await session.call_tool(
                "update_line_transcription",
                {
                    "target": {
                        "document_id": 4,
                        "page_id": 10,
                        "line_transcription_id": 91,
                    },
                    "changes": changes,
                },
            )
            # Then scope and uniqueness checks reject it before PATCH.
            assert result.is_error

    with transcription_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _route, _body in fixture.requests)
    row = fixture.records[0]
    assert isinstance(row, dict)
    assert (row["line"], row["transcription"]) == (11, 2)


def test_single_link_change_preserves_scoped_record_identity_and_history() -> None:
    # Given a new unoccupied line/layer pair in the same document and page.
    changes: dict[str, JsonValue] = {"line": 12, "transcription": 3}

    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When changing both links after scope preflight.
            result = await invoke(
                session,
                "update_line_transcription",
                {
                    "target": {
                        "document_id": 4,
                        "page_id": 10,
                        "line_transcription_id": 91,
                    },
                    "changes": changes,
                },
            )
            # Then only the links change; the text row's identity survives.
            assert isinstance(result, dict)
            assert (result["pk"], result["line"], result["transcription"]) == (
                91,
                12,
                3,
            )
            assert result["content"] == "old"
            assert result["versions"] == [{"content": "history"}]

    with transcription_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("PATCH", TEXTS + "91/", changes)
    assert all(method == "GET" for method, _route, _body in fixture.requests[:-1])


@pytest.mark.parametrize("protected", [False, True])
def test_layer_delete_archives_and_preserves_protected_error(
    *, protected: bool
) -> None:
    # Given a normal layer or the server-protected manual layer.
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            # When the published delete tool calls the native archival endpoint.
            result = await session.call_tool(
                "delete_transcription",
                {
                    "document_id": 4,
                    "transcription_id": 2,
                },
            )
            # Then success/error reflects the real upstream result.
            assert bool(result.is_error) is protected
            if protected:
                block = result.content[0]
                assert isinstance(block, TextContent)
                assert "400" in block.text

    with transcription_fixture() as fixture:
        if protected:
            fixture.failures[LAYER] = 400
        anyio.run(run, fixture)
    assert fixture.requests == [("DELETE", LAYER, {})]
    assert fixture.layer["archived"] is not protected
    assert len(fixture.records) == 2
