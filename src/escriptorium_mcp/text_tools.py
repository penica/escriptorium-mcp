"""MCP transcription creation, correction and removal."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, Input, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.record_models import LineText, Rename, TextPatch


def register_text(server: MCPServer) -> None:
    """Register tools scoped to transcription layers and line text."""

    @server.tool(annotations=CREATE)
    async def create_line_transcription(
        document_id: Identifier,
        page_id: Identifier,
        text: LineText,
    ) -> JsonValue:
        """Write text for an existing segmented line in a transcription layer."""
        return await invoke(
            "POST", f"documents/{document_id}/parts/{page_id}/transcriptions/", text
        )

    @server.tool(annotations=CHANGE)
    async def update_line_transcription(
        target: TextTarget,
        changes: TextPatch,
    ) -> JsonValue:
        """Correct an existing line transcription by its record PK, not its line PK."""
        return await invoke("PATCH", target.route(), changes)

    @server.tool(annotations=CHANGE)
    async def rename_transcription(
        document_id: Identifier,
        transcription_id: Identifier,
        changes: Rename,
    ) -> JsonValue:
        """Rename a transcription layer without rewriting its line text."""
        return await invoke(
            "PATCH",
            f"documents/{document_id}/transcriptions/{transcription_id}/",
            changes,
        )

    @server.tool(annotations=DELETE)
    async def delete_transcription(
        document_id: Identifier,
        transcription_id: Identifier,
    ) -> JsonValue:
        """Delete a transcription layer and its line text according to server rules."""
        return await invoke(
            "DELETE", f"documents/{document_id}/transcriptions/{transcription_id}/"
        )

    @server.tool(annotations=DELETE)
    async def delete_line_transcription(target: TextTarget) -> JsonValue:
        """Delete one line transcription record, keeping its segmented line."""
        return await invoke("DELETE", target.route())


class TextTarget(Input):
    """The complete address of one line transcription record."""

    document_id: Identifier
    page_id: Identifier
    line_transcription_id: Identifier

    def route(self) -> str:
        """Build its relative API path."""
        return (
            f"documents/{self.document_id}/parts/{self.page_id}/"
            f"transcriptions/{self.line_transcription_id}/"
        )
