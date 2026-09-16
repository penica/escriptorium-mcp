"""Scoped native export submission without inferring asynchronous completion."""

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, JsonValue

from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.file_models import ServerExport
from escriptorium_mcp.text_scope import RecordId, collection


class ExportDocument(RecordId):
    """Enabled region identities permitted by the native document export form."""

    valid_block_types: list[RecordId] = Field(default_factory=list)


class ExportLayer(RecordId):
    """The required selected layer must be visible and active, even for all layers."""

    archived: bool


async def submit_export(document_id: Identifier, export: ServerExport) -> JsonValue:
    """Check current scope, submit exactly once and preserve the native response."""
    document = ExportDocument.model_validate(
        await invoke("GET", f"documents/{document_id}/")
    )
    if document.pk != document_id:
        msg = "The server returned a different document; no export was submitted."
        raise ToolError(msg)
    layer = ExportLayer.model_validate(
        await invoke(
            "GET", f"documents/{document_id}/transcriptions/{export.transcription}/"
        )
    )
    if layer.pk != export.transcription or layer.archived:
        msg = "Select an active, visible transcription in the requested document."
        raise ToolError(msg)
    if export.parts is not None:
        known = {
            RecordId.model_validate(row).pk
            for row in await collection(f"documents/{document_id}/parts/")
        }
        if not set(export.parts).issubset(known):
            msg = "An export page is outside the requested document."
            raise ToolError(msg)
    if export.region_types is not None:
        allowed: set[int | str] = {row.pk for row in document.valid_block_types} | {
            "Undefined",
            "Orphan",
        }
        if not set(export.region_types).issubset(allowed):
            msg = "An export region type is not enabled for the requested document."
            raise ToolError(msg)
    request = ApiRequest(
        method="POST",
        route=f"documents/{document_id}/export/",
        body_json=export.model_dump_json(
            exclude_none=True,
            exclude=set(type(export).model_fields)
            - export.model_fields_set
            - {"transcription", "file_format", "include_characters"},
        ),
    )
    try:
        return await call(request, timeout_seconds=1800)
    except ToolError as error:
        msg = (
            f"{error} An export task may already be queued. Inspect task reports "
            "and generated downloads before retrying; no automatic retry occurred."
        )
        raise ToolError(msg) from None
