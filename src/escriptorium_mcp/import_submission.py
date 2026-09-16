"""Scoped source mapping and one native import submission with optional tracking."""

from typing import Literal, assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import HttpUrl, JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.api import ApiRequest, Input, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.import_models import (
    IiifUrl,
    ImportName,
    ImportSource,
    MetsFile,
    MetsUrl,
    PdfFile,
    XmlFile,
)
from escriptorium_mcp.submission_tracking import SubmissionGroup, read_submission_groups
from escriptorium_mcp.task_monitoring import IMPORT_METHOD
from escriptorium_mcp.text_scope import RecordId


class ImportLayer(RecordId):
    """Only a scoped, visible layer with a storable name can select an import target."""

    name: str


class NativeImport(Input):
    """Serializer fields; absent options stay absent in JSON and multipart forms."""

    mode: Literal["pdf", "xml", "iiif", "mets"]
    mets_type: Literal["local", "url"] | None = None
    iiif_uri: HttpUrl | None = None
    mets_uri: HttpUrl | None = None
    name: ImportName | None = None
    transcription: Identifier | None = None
    override: bool | None = None


async def prepare_import(document_id: Identifier, source: ImportSource) -> ApiRequest:
    """Check scope before constructing a single native write; checks are not locks."""
    document = RecordId.model_validate(await invoke("GET", f"documents/{document_id}/"))
    if document.pk != document_id:
        msg = "The server returned a different document; no import was submitted."
        raise ToolError(msg)
    file_path = None
    match source:
        case PdfFile():
            file_path = source.file_path
            body = NativeImport(mode="pdf")
        case XmlFile():
            file_path = source.file_path
            body = NativeImport(
                mode="xml",
                name=source.name,
                transcription=source.transcription_id,
                override=source.override,
            )
        case IiifUrl():
            body = NativeImport(mode="iiif", iiif_uri=source.url)
        case MetsFile():
            file_path = source.file_path
            body = NativeImport(
                mode="mets",
                mets_type="local",
                name=source.name,
                transcription=source.prefix_transcription_id,
                override=source.override,
            )
        case MetsUrl():
            body = NativeImport(
                mode="mets",
                mets_type="url",
                mets_uri=source.url,
                name=source.name,
                transcription=source.prefix_transcription_id,
                override=source.override,
            )
        case _:
            assert_never(source)
    if body.transcription is not None:
        layer = ImportLayer.model_validate(
            await invoke(
                "GET", f"documents/{document_id}/transcriptions/{body.transcription}/"
            )
        )
        if layer.pk != body.transcription:
            msg = "Select a visible transcription in the requested document."
            raise ToolError(msg)
        try:
            _ = TypeAdapter[str](ImportName).validate_python(layer.name)
        except ValidationError:
            msg = "The selected layer name must be nonblank and at most 256 characters."
            raise ToolError(msg) from None
    return ApiRequest(
        method="POST",
        route=f"documents/{document_id}/import/",
        body_json=body.model_dump_json(exclude_none=True),
        file_path=file_path,
        file_field="upload_file",
    )


async def submit_import(
    document_id: Identifier, source: ImportSource, *, track: bool
) -> JsonValue:
    """Submit once and never turn failed follow-up monitoring into a failed write."""
    request = await prepare_import(document_id, source)
    before = await read_submission_groups(document_id) if track else None
    try:
        submission = await call(request, timeout_seconds=1800)
    except ToolError as error:
        msg = (
            f"{error} Import records or a queued task may already exist. "
            "Inspect import reports and groups before retrying; "
            "no automatic retry occurred."
        )
        raise ToolError(msg) from None
    if not track:
        return submission
    after = await read_submission_groups(document_id)
    candidates: list[SubmissionGroup] = []
    status = "unavailable"
    if before is not None and after is not None:
        previous_ids = {group.pk for group in before}
        candidates = [
            group
            for group in after
            if group.pk not in previous_ids and group.method in {None, IMPORT_METHOD}
        ]
        status = "none"
        if candidates:
            status = "candidate" if len(candidates) == 1 else "ambiguous"
    return {
        "accepted": True,
        "submission": submission,
        "tracking": {
            "status": status,
            "candidates": [group.as_json() for group in candidates],
            "attribution_confirmed": False,
            "limitations": (
                "Import submission returns no import/task/group ID. New groups are "
                "only candidates, including a single match. Concurrent submissions, "
                "delayed reports and failed reads prevent reliable attribution. "
                "Acceptance is not completion. Do not resubmit to fix monitoring."
            ),
        },
    }
