"""Explicit modern imports while keeping the legacy file-import tool available."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import JOB
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.import_models import ImportSource
from escriptorium_mcp.import_submission import submit_import


def register_imports(server: MCPServer) -> None:
    """Register source-specific native submission with honest acceptance reporting."""

    @server.tool(annotations=JOB)
    async def submit_document_import(
        document_id: Identifier, source: ImportSource, *, track: bool = False
    ) -> JsonValue:
        """Submit PDF, XML/ZIP, IIIF or METS through the modern document import API.

        Local file_path must exist on the MCP host. URLs are fetched by eScriptorium
        under its network policy; MCP does not download them or forward API tokens.
        IIIF supports Presentation 2 image-service manifests, all canvases; PDF and
        IIIF import images only. No Presentation 3 or JSON archive restore is offered.

        XML transcription_id selects a visible document layer by its name;
        name selects/creates a layer. METS name or prefix_transcription_id supplies
        a prefix for separate source layers, not an exact destination layer. Use
        absolute references in local METS XML or a self-contained METS ZIP.

        XML matches pages by original_filename; unmatched pages produce warnings.
        Even override=false can replace text/images. override=true deletes page
        lines/regions and their text/history across ALL layers. Image replacement
        does not promise geometry reprojection. Multi-page imports are not atomic.

        Success means accepted, not complete. Inspect reports for skipped-file
        warnings and separate image-conversion jobs. track=true returns uncertain
        new group candidates, never confirmed attribution. Native processed/total
        counters are unavailable; monitoring failure never warrants resubmission.
        """
        return await submit_import(document_id, source, track=track)
