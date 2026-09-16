"""Discovery, local retrieval and deletion of generated export artifacts."""

from pathlib import Path
from typing import assert_never

from mcp.server import MCPServer
from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp.api import CREATE, DELETE, READ
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.download_models import (
    DownloadDelete,
    DownloadFile,
    DownloadGet,
    DownloadList,
    DownloadReportPage,
    DownloadReportRecord,
    Fingerprint,
)


def register_downloads(server: MCPServer) -> None:
    """Expose the authenticated user's generated-download records and files."""

    @server.tool(annotations=READ)
    async def list_downloads(task_report_id: Identifier | None = None) -> JsonValue:
        """List all current-user download records, following every page safely.

        task_report_id filters locally after pagination. A nonnull report ID links
        an artifact to that report, not to an unconfirmed submission. Expired rows
        may remain visible; absence does not prove an export failed. Without a
        filter the native collection shape and metadata are preserved.
        """
        raw = await call(DownloadList())
        if task_report_id is None:
            return raw
        parsed = TypeAdapter[list[DownloadReportRecord] | DownloadReportPage](
            list[DownloadReportRecord] | DownloadReportPage
        ).validate_python(raw)
        match parsed:
            case DownloadReportPage(results=records):
                selected = records
            case list():
                selected = parsed
            case _:
                assert_never(parsed)
        results = [
            record.as_json()
            for record in selected
            if record.task_report_id == task_report_id
        ]
        return {
            "count": len(results),
            "next": None,
            "previous": None,
            "results": results,
        }

    @server.tool(annotations=READ)
    async def get_download(fingerprint: Fingerprint) -> JsonValue:
        """Read owned download metadata without incrementing file access counters.

        fingerprint is exactly 32 lowercase hexadecimal characters. Expired rows
        can still have metadata while file retrieval returns 404. Metadata does
        not prove stored bytes exist; server-reported file_url is informational.
        """
        return await call(DownloadGet(fingerprint=fingerprint))

    @server.tool(annotations=CREATE)
    async def download_generated_export(
        fingerprint: Fingerprint, destination: Path
    ) -> JsonValue:
        """Save a generated export to a new file on the MCP server's host.

        Verify metadata identity and byte size, then stream through the fixed
        authenticated file route; file_url cannot choose the request destination.
        File access increments server counters. Destination and .part must be new,
        use portable names and stay outside the scan-only Books archive. Failed
        transfers retain partial files. Return bytes/SHA-256 only after exclusive
        publication; that checksum proves local bytes, not archive completeness.
        Expired or missing files return errors. Redirects and retries are refused.
        """
        return await call(
            DownloadFile(fingerprint=fingerprint, destination=destination),
            timeout_seconds=1800,
        )

    @server.tool(annotations=DELETE)
    async def delete_download(fingerprint: Fingerprint) -> JsonValue:
        """Delete one owned download record and ask eScriptorium to unlink its file.

        The native bodyless 204 is success; the request is not retried. Upstream
        can suppress file-removal failures, so success does not prove secure
        erasure or physical removal. Save needed bytes before deleting the record.
        """
        return await call(DownloadDelete(fingerprint=fingerprint))
