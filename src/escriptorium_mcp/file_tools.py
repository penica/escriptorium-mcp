"""Uploads, exports and NAS register acquisition."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CREATE, JOB, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.file_models import (
    DocumentImport,
    ExportDownload,
    ImportMetadata,
    RegisterDownload,
    ServerExport,
    TranscriptionExport,
)


def register_files(server: MCPServer) -> None:
    """Register file operations without embedding image bytes in MCP messages."""

    @server.tool(annotations=CREATE)
    async def download_register(register: RegisterDownload) -> JsonValue:
        """Download ALL available scans directly to NAS with a checksum manifest.

        Requires a new catalogue folder. Existing destinations are never overwritten.
        Download completion does not mean visual inspection or transcription completion.
        """
        return await call(register, timeout_seconds=21600)

    @server.tool(annotations=CREATE)
    async def export_transcriptions(export: TranscriptionExport) -> JsonValue:
        """Save a layer as UTF-8 text or JSON locally in page/line order.

        Works with API-token authentication without waiting for server notifications.
        Existing files are never overwritten. JSON preserves line IDs and revisions.
        """
        return await call(export, timeout_seconds=1800)

    @server.tool(annotations=CREATE)
    async def request_server_export(
        document_id: Identifier, export: ServerExport
    ) -> JsonValue:
        """Queue a native ALTO, PAGE XML or text archive export.

        Success means queued, not complete. Use the URL in the eScriptorium completion
        notification with download_export. This instance has no downloads-list API.
        """
        return await call(
            ApiRequest(
                method="POST",
                route=f"documents/{document_id}/export/",
                body_json=export.model_dump_json(exclude_none=True),
            )
        )

    @server.tool(annotations=CREATE)
    async def download_export(export: ExportDownload) -> JsonValue:
        """Save a completed same-server export URL to a new local file with checksum."""
        return await call(export, timeout_seconds=1800)

    @server.tool(annotations=JOB)
    async def import_document_file(
        document_id: Identifier, upload: DocumentImport
    ) -> JsonValue:
        """Queue import of PDF, ZIP, ALTO or PAGE XML into an existing document.

        override=true can replace segmentation and text. Poll task reports afterward.
        """
        metadata = ImportMetadata(name=upload.name, override=upload.override)
        return await call(
            ApiRequest(
                method="POST",
                route=f"documents/{document_id}/imports/",
                file_path=upload.file_path,
                file_field="upload_file",
                body_json=metadata.model_dump_json(),
            ),
            timeout_seconds=1800,
        )
