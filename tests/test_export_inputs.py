"""Export input boundaries reject meaningless or ambiguous native selections."""

import anyio
import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.file_models import ServerExport
from tests.export_submission_fixture import (
    ExportFixture,
    export_fixture,
    export_session,
)


@pytest.mark.parametrize(
    "patch",
    [
        {"transcription": 0},
        {"transcription": True},
        {"transcription": "2"},
        {"file_format": "pdf"},
        {"archive_format": "tgz", "file_format": "json"},
        {"parts": []},
        {"parts": [11, 11]},
        {"parts": [0]},
        {"parts": [True]},
        {"region_types": []},
        {"region_types": [3, 3]},
        {"region_types": ["Orphan", "Orphan"]},
        {"region_types": [0]},
        {"region_types": [-1]},
        {"region_types": [True]},
        {"region_types": ["3"]},
        {"region_types": ["undefined"]},
        {"unknown": True},
    ],
)
def test_invalid_selections(patch: dict[str, JsonValue]) -> None:
    # Given supplied IDs/formats that cannot identify a unique native selection.
    request: dict[str, JsonValue] = {"transcription": 2}
    request.update(patch)
    # When parsing the public export input, then invalid state is rejected.
    with pytest.raises(ValidationError):
        _ = ServerExport.model_validate(request)


@pytest.mark.parametrize(
    "field",
    [
        "include_images",
        "include_metadata",
        "include_models",
        "all_transcriptions",
        "include_annotations",
        "anonymize",
        "archive_format",
    ],
)
def test_new_optional_fields_reject_explicit_null(field: str) -> None:
    # Given omission-compatible options whose explicitly supplied value is null.
    request: dict[str, JsonValue] = {
        "transcription": 2,
        "file_format": "json",
        field: None,
    }
    # When parsed, then null never silently becomes a valid native setting.
    with pytest.raises(ValidationError):
        _ = ServerExport.model_validate(request)


@pytest.mark.parametrize(
    "field",
    [
        "include_metadata",
        "include_models",
        "all_transcriptions",
        "include_annotations",
        "anonymize",
    ],
)
def test_json_only_features_reject_non_json_export(field: str) -> None:
    # Given a true archive-only option on the default ALTO exporter.
    # When parsed, then the request cannot claim an option upstream ignores.
    with pytest.raises(ValidationError):
        _ = ServerExport.model_validate({"transcription": 2, field: True})
    assert ServerExport.model_validate({"transcription": 2, field: False})


@pytest.mark.parametrize("file_format", ["text", "openitimarkdown", "teixml"])
def test_image_flag_requires_supporting_exporter(file_format: str) -> None:
    # Given an exporter that does not include requested images.
    # When parsed, then the ineffective true option is rejected.
    with pytest.raises(ValidationError):
        _ = ServerExport.model_validate(
            {
                "transcription": 2,
                "file_format": file_format,
                "include_images": True,
            }
        )


def test_explicit_archive_format_requires_json() -> None:
    # Given an archive choice on a non-JSON format.
    # When parsed, then even explicit zip is rejected instead of ignored.
    with pytest.raises(ValidationError):
        _ = ServerExport.model_validate({"transcription": 2, "archive_format": "zip"})


def test_invalid_mcp_input_never_reaches_upstream() -> None:
    # Given a real STDIO client with a duplicate page selection.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When MCP arguments are validated.
            result = await session.call_tool(
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {"transcription": 2, "parts": [11, 11]},
                },
            )
            # Then the client receives a validation error before network work.
            assert result.is_error

    with export_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
