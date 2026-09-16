"""Native export formats and options across the real STDIO MCP boundary."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.export_submission_fixture import (
    EXPORT,
    ExportFixture,
    export_fixture,
    export_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_json_archive_preserves_all_native_fields() -> None:
    # Given a document with an active layer and enabled region types.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When the complete native archive preset is requested.
            result = await invoke(
                session,
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {
                        "transcription": 2,
                        "file_format": "json",
                        "include_images": True,
                        "include_characters": True,
                        "include_metadata": True,
                        "include_models": True,
                        "all_transcriptions": True,
                        "include_annotations": True,
                        "anonymize": True,
                        "archive_format": "tar.gz",
                    },
                },
            )
            # Then acceptance stays the native response without invented job IDs.
            assert result == {"status": "ok"}

    with export_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r for r in fixture.requests if r[0] == "POST"] == [
        (
            "POST",
            EXPORT,
            {
                "transcription": 2,
                "file_format": "json",
                "include_images": True,
                "include_characters": True,
                "include_metadata": True,
                "include_models": True,
                "all_transcriptions": True,
                "include_annotations": True,
                "anonymize": True,
                "archive_format": "tar.gz",
                "region_types": [3, 7, "Undefined", "Orphan"],
            },
        )
    ]


@pytest.mark.parametrize(
    "file_format", ["alto", "pagexml", "text", "json", "openitimarkdown", "teixml"]
)
def test_native_formats_keep_explicit_scope(file_format: str) -> None:
    # Given a selected page and explicit region subset.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When a native format is submitted.
            result = await invoke(
                session,
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {
                        "transcription": 2,
                        "file_format": file_format,
                        "parts": [12],
                        "region_types": [7, "Orphan"],
                    },
                },
            )
            # Then the server acceptance remains unembellished.
            assert result == {"status": "ok"}

    with export_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        EXPORT,
        {
            "transcription": 2,
            "file_format": file_format,
            "parts": [12],
            "region_types": [7, "Orphan"],
            "include_characters": False,
        },
    )


def test_legacy_defaults_and_null_scope_keep_all_regions() -> None:
    # Given a legacy call using null as an omitted page/region selection.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When only the required layer is supplied with legacy nulls.
            result = await invoke(
                session,
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {"transcription": 2, "parts": None, "region_types": None},
                },
            )
            # Then historical defaults survive.
            assert result == {"status": "ok"}

    with export_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        EXPORT,
        {
            "transcription": 2,
            "file_format": "alto",
            "include_characters": False,
            "region_types": [3, 7, "Undefined", "Orphan"],
        },
    )


def test_explicit_false_options_and_zip_are_preserved() -> None:
    # Given JSON with explicitly disabled inclusion fields and an orphan-only scope.
    settings: dict[str, JsonValue] = {
        "transcription": 2,
        "file_format": "json",
        "archive_format": "zip",
        "include_images": False,
        "include_characters": False,
        "include_metadata": False,
        "include_models": False,
        "all_transcriptions": False,
        "include_annotations": False,
        "anonymize": False,
        "region_types": ["Orphan"],
    }

    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When the request crosses the MCP and worker boundaries.
            result = await invoke(
                session,
                "request_server_export",
                {
                    "document_id": 4,
                    "export": settings,
                },
            )
            # Then success denotes acceptance only.
            assert result == {"status": "ok"}

    with export_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", EXPORT, settings)


def test_historical_text_character_flag_is_accepted() -> None:
    # Given the formerly accepted text/character combination, ignored upstream.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When the unchanged client arguments are submitted.
            result = await invoke(
                session,
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {
                        "transcription": 2,
                        "file_format": "text",
                        "include_characters": True,
                    },
                },
            )
            # Then compatibility is retained without changing the format.
            assert result == {"status": "ok"}

    with export_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        EXPORT,
        {
            "transcription": 2,
            "file_format": "text",
            "include_characters": True,
            "region_types": [3, 7, "Undefined", "Orphan"],
        },
    )


@pytest.mark.parametrize("status", [400, 403, 500])
def test_submission_error_has_one_post_and_no_fallback(status: int) -> None:
    # Given an endpoint rejecting a gated format or failing after job submission.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When the server rejects the single native export request.
            result = await session.call_tool(
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {"transcription": 2, "file_format": "teixml"},
                },
            )
            # Then it is an error with queue uncertainty rather than a fallback job.
            assert result.is_error
            assert "queued" in result.model_dump_json().lower()

    with export_fixture() as fixture:
        fixture.failures[EXPORT] = status
        anyio.run(run, fixture)
    assert len([r for r in fixture.requests if r[0] == "POST"]) == 1
    assert fixture.requests[-1][2] == {
        "transcription": 2,
        "file_format": "teixml",
        "include_characters": False,
        "region_types": [3, 7, "Undefined", "Orphan"],
    }


def test_lost_acceptance_is_not_retried() -> None:
    # Given an export endpoint that receives the job but loses the response.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When the connection closes after request acceptance.
            result = await session.call_tool(
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {"transcription": 2},
                },
            )
            # Then callers see uncertainty and no synthetic success identity.
            assert result.is_error
            assert "queued" in result.model_dump_json().lower()

    with export_fixture() as fixture:
        fixture.disconnect.add(EXPORT)
        anyio.run(run, fixture)
    assert len([r for r in fixture.requests if r[0] == "POST"]) == 1
