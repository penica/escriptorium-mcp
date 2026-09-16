"""Native bulk transcription actions with scoped preflight and no write retries."""

from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, JOB, Input, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.record_models import LineText
from escriptorium_mcp.text_models import BulkTextPatch
from escriptorium_mcp.text_scope import (
    preflight_clear,
    preflight_create,
    preflight_update,
)

CreateLines = Annotated[list[LineText], Field(min_length=1)]
UpdateLines = Annotated[list[BulkTextPatch], Field(min_length=1)]
RecordIds = Annotated[list[Identifier], Field(min_length=1)]


class BulkCreate(Input):
    """The server requires a lines wrapper rather than a bare JSON array."""

    lines: CreateLines


class BulkUpdate(Input):
    """Existing text-record PKs and only the supplied changes."""

    lines: UpdateLines


class BulkClear(Input):
    """Native bulk_delete takes text-record IDs, not segmented-line IDs."""

    lines: RecordIds


def register_text_bulk(server: MCPServer) -> None:
    """Expose native bulk actions without inventing atomicity or revision history."""

    @server.tool(annotations=CREATE)
    async def bulk_create_line_transcriptions(
        document_id: Identifier, page_id: Identifier, lines: CreateLines
    ) -> JsonValue:
        """Create line text/graphs in bulk after checking page and layer membership.

        Reject duplicate line/layer pairs. Server normalization is preserved.
        The native bulk path does not run single-create progress/author hooks.
        Preflight is not a lock; inspect remote state before retrying a failure.
        """
        route = await preflight_create(document_id, page_id, lines)
        return await invoke("POST", route + "bulk_create/", BulkCreate(lines=lines))

    @server.tool(annotations=JOB)
    async def bulk_update_line_transcriptions(
        document_id: Identifier, page_id: Identifier, lines: UpdateLines
    ) -> JsonValue:
        """Update existing text-record PKs, checking all page/layer references first.

        This native operation is non-atomic: a failed response can follow saved
        earlier rows. No automatic retry. Re-read records after any failure.
        Omit unchanged fields; null clears graphs/average confidence only.
        Pause concurrent writers during preflight and submission.
        """
        route = await preflight_update(document_id, page_id, lines)
        try:
            return await invoke("PUT", route + "bulk_update/", BulkUpdate(lines=lines))
        except ToolError as error:
            msg = (
                "Bulk update may have partially applied changes. "
                f"Re-read the affected records before retrying. {error}"
            )
            raise ToolError(msg) from None

    @server.tool(annotations=CHANGE)
    async def bulk_clear_line_transcriptions(
        document_id: Identifier, page_id: Identifier, line_transcription_ids: RecordIds
    ) -> JsonValue:
        """Blank selected text records through native bulk_delete; keep their rows.

        This clears content only. Graphs, confidence and existing history remain;
        the native action creates no history revision. IDs are text-record PKs,
        not segmented-line IDs. Preflight checks membership but is not a lock.
        """
        route = await preflight_clear(document_id, page_id, line_transcription_ids)
        return await invoke(
            "POST", route + "bulk_delete/", BulkClear(lines=line_transcription_ids)
        )
