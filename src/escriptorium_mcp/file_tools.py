"""Uploads, exports and NAS register acquisition."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CREATE, JOB, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.export_submission import submit_export
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
        Existing files are never overwritten. JSON preserves line IDs and revisions;
        this is a layer export, not the native full-document JSON archive.
        """
        return await call(export, timeout_seconds=1800)

    @server.tool(annotations=CREATE)
    async def request_server_export(
        document_id: Identifier, export: ServerExport
    ) -> JsonValue:
        """Queue native ALTO, PAGE XML, text, JSON, OpenITI or TEI export once.

        OpenITI/TEI require server enablement. Omitted pages and region types mean
        all; the selected transcription must be active even with all_transcriptions.
        JSON supports ZIP/tar.gz, metadata, annotations, model catalogue metadata
        (not weights), all layers including archived ones, and partial author-name
        anonymization. Missing images may be skipped. JSON has no native restore.
        Character boxes apply to ALTO/PAGE/JSON and may be invalidated by editing.
        Success means accepted, not complete, and returns no task/group/download ID.
        Inspect document task reports and list_downloads; download.task_report_id
        links a file to its report, not to this submission. Completion notifications
        can also supply a URL for download_export. No automatic retry is performed.
        """
        return await submit_export(document_id, export)

    @server.tool(annotations=CREATE)
    async def download_export(export: ExportDownload) -> JsonValue:
        """Save a completed same-server export URL to a new local file with checksum."""
        return await call(export, timeout_seconds=1800)

    @server.tool(annotations=JOB)
    async def import_document_file(
        document_id: Identifier, upload: DocumentImport
    ) -> JsonValue:
        """Queue PDF, ZIP, ALTO or PAGE XML through the legacy plural import form.

        Use submit_document_import for explicit modes, IIIF/METS and layer IDs.
        Local paths refer to the MCP host. Even override=false may replace text or
        matching images. override=true deletes segmentation and attached text/history
        across layers. Submission is not completion; inspect task reports for errors
        and skipped files. No automatic retry or resume is performed by this tool.
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
