"""Layer settings, stored-character statistics and page lookup."""

from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.text_models import Character, LayerPatch


def register_text_reads(server: MCPServer) -> None:
    """Register layer metadata and server-computed text statistics."""

    @server.tool(annotations=READ)
    async def get_transcription(
        document_id: Identifier, transcription_id: Identifier
    ) -> JsonValue:
        """Read a document's transcription layer, comments and archived state."""
        return await invoke(
            "GET", f"documents/{document_id}/transcriptions/{transcription_id}/"
        )

    @server.tool(annotations=CHANGE)
    async def update_transcription(
        document_id: Identifier, transcription_id: Identifier, changes: LayerPatch
    ) -> JsonValue:
        """Edit layer name, archived state, comments or average-confidence metadata.

        Omit unchanged fields; null clears comments/average confidence. Archiving
        hides a layer but retains its line records. This does not recompute scores.
        """
        return await invoke(
            "PATCH",
            f"documents/{document_id}/transcriptions/{transcription_id}/",
            changes,
        )

    @server.tool(annotations=READ)
    async def get_transcription_statistics(
        document_id: Identifier,
        transcription_id: Identifier,
        ordering: Literal["frequency", "-frequency", "char", "-char"] = "-frequency",
    ) -> JsonValue:
        """Return nonempty-line count and stored-character frequencies for a layer.

        Sum the returned frequencies for the stored-character count. Stored
        markup is included; these are not normalized plain-text/grapheme counts.
        The server caches statistics for up to one hour. Preserve zero counts.
        """
        route = f"documents/{document_id}/transcriptions/{transcription_id}/"
        _ = await invoke("GET", route)
        return await call(
            ApiRequest(
                method="GET", route=route + "stats/", query={"ordering": ordering}
            )
        )

    @server.tool(annotations=READ)
    async def find_transcription_pages_by_character(
        document_id: Identifier, transcription_id: Identifier, character: Character
    ) -> JsonValue:
        """Locate pages containing one stored Unicode code point in a layer.

        Requires the newer parts_by_char endpoint. A multi-code-point grapheme
        must be queried by individual code point; stored markup is included.
        Page IDs and per-page counts come directly from the server.
        """
        route = f"documents/{document_id}/transcriptions/{transcription_id}/"
        _ = await invoke("GET", route)
        try:
            return await call(
                ApiRequest(
                    method="GET",
                    route=route + "parts_by_char/",
                    query={"char": character},
                )
            )
        except ToolError as error:
            if "HTTP 404" not in str(error):
                raise
            msg = (
                "Character-to-page lookup is unavailable or hidden for this layer "
                "(HTTP 404). This does not identify the server version."
            )
            raise ToolError(msg) from None
