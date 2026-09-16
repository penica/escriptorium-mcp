"""Nullable font identifiers retain strict input boundaries and omission semantics."""

import anyio
import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.project_models import ProjectCreateSettings, ProjectPatch
from escriptorium_mcp.record_models import DocumentCreate, DocumentPatch
from tests.font_fixture import FontFixture, font_fixture, font_session
from tests.font_write_cases import OPERATIONS, Operation, write_case


@pytest.mark.parametrize("font_id", [True, "3", 0, -1, 1.5])
def test_record_font_models_reject_nonidentifiers(font_id: JsonValue) -> None:
    # Given coercible or nonpositive values outside the native font identity contract.
    data = {"transcription_font": font_id}
    # When parsed by every extended record input, then validation rejects them.
    with pytest.raises(ValidationError):
        _ = ProjectCreateSettings.model_validate(data)
    with pytest.raises(ValidationError):
        _ = ProjectPatch.model_validate(data)
    with pytest.raises(ValidationError):
        _ = DocumentPatch.model_validate(data)
    with pytest.raises(ValidationError):
        _ = DocumentCreate.model_validate(
            {"name": "New", "project": "old", "main_script": "Latin", **data}
        )


def test_document_patch_nullable_font_keeps_other_fields_nonnullable() -> None:
    # Given the new nullable font alongside existing non-nullable document settings.
    # When the field is null, then validation neither crashes nor drops it.
    assert DocumentPatch.model_validate({"transcription_font": None}).model_dump(
        exclude_unset=True
    ) == {"transcription_font": None}
    assert DocumentPatch.model_validate(
        {"transcription_font": 3, "name": "New"}
    ).model_dump(exclude_unset=True) == {"transcription_font": 3, "name": "New"}
    with pytest.raises(ValidationError):
        _ = DocumentPatch.model_validate({"transcription_font": None, "name": None})
    with pytest.raises(ValidationError):
        _ = DocumentPatch.model_validate({})


@pytest.mark.parametrize("operation", OPERATIONS)
def test_invalid_font_is_rejected_before_any_io(operation: Operation) -> None:
    # Given an invalid boolean font ID submitted through each public MCP operation.
    case = write_case(operation, {"transcription_font": True})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the call is decoded, then no capability query or write is sent.
            assert (await session.call_tool(case.tool, case.arguments)).is_error

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
