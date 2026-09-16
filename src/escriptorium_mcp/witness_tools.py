"""Owned textual witness management and safe local file transfers."""

import json
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import HttpUrl, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.file_models import ExportDownload
from escriptorium_mcp.settings import load_settings
from escriptorium_mcp.witness_files import witness_file_url
from escriptorium_mcp.witness_models import WitnessPatch, WitnessUpload
from escriptorium_mcp.witness_scope import read_witness, validate_witness_file
from escriptorium_mcp.witness_upload import submit_witness


async def _mutate(request: ApiRequest) -> JsonValue:
    """Do not repeat a possibly applied witness update or deletion after failure."""
    try:
        return await call(request, timeout_seconds=1800)
    except ToolError as error:
        msg = (
            f"{error} The textual witness may already have changed. "
            "Inspect its state before retrying; no automatic retry occurred."
        )
        raise ToolError(msg) from None


def register_witnesses(server: MCPServer) -> None:
    """Register account-owned witness CRUD and file retrieval."""

    @server.tool(annotations=READ)
    async def list_textual_witnesses() -> JsonValue:
        """List all current-user-owned witnesses with full strict pagination."""
        return await call(
            ApiRequest(
                method="GET",
                route="textual-witnesses/",
                paginate=True,
                strict_pagination=True,
            )
        )

    @server.tool(annotations=READ)
    async def get_textual_witness(witness_id: Identifier) -> JsonValue:
        """Read owned witness metadata, retaining native fields and file references."""
        return await read_witness(witness_id)

    @server.tool(annotations=CREATE)
    async def upload_textual_witness(upload: WitnessUpload) -> JsonValue:
        """Upload UTF-8 .txt once, acknowledging uncertain native owner assignment.

        Some server versions create ownerless inaccessible witnesses. Required
        acknowledge_unverified_ownership=true accepts that risk. A successful
        native POST is reported as accepted separately from one ownership
        readback; failed readback never hides acceptance or triggers a retry.
        """
        return await submit_witness(upload)

    @server.tool(annotations=CHANGE)
    async def update_textual_witness(
        witness_id: Identifier, changes: WitnessPatch
    ) -> JsonValue:
        """Rename or replace an owned witness file, preserving omitted fields.

        Replacement keeps exact UTF-8 bytes and can affect queued consumers.
        It does not rewrite completed alignment output or promise rollback.
        """
        if changes.file_path is not None:
            await validate_witness_file(changes.file_path, standalone=True)
        _ = await read_witness(witness_id)
        metadata = {"name": changes.name} if changes.name is not None else {}
        return await _mutate(
            ApiRequest(
                method="PATCH",
                route=f"textual-witnesses/{witness_id}/",
                body_json=json.dumps(metadata),
                file_path=changes.file_path,
                file_field="file",
                single_attempt=True,
            )
        )

    @server.tool(annotations=DELETE)
    async def delete_textual_witness(witness_id: Identifier) -> JsonValue:
        """Delete an owned witness; queued consumers may fail afterward.

        Deletion does not cancel jobs or guarantee secure physical file erasure.
        """
        _ = await read_witness(witness_id)
        return await _mutate(
            ApiRequest(
                method="DELETE",
                route=f"textual-witnesses/{witness_id}/",
                single_attempt=True,
            )
        )

    @server.tool(annotations=CREATE)
    async def download_textual_witness(
        witness_id: Identifier, destination: Path
    ) -> JsonValue:
        """Save owned witness bytes to a new file outside the scan-only Books archive.

        Destination and .part must be unused; interrupted partials are preserved.
        Return byte count and local SHA-256 after completion, without claiming
        a native checksum exists. Foreign, signed or redirected URLs are refused.
        """
        record = await read_witness(witness_id)
        url = witness_file_url(record, str(load_settings().url))
        return await call(
            ExportDownload(url=HttpUrl(url), destination=destination),
            timeout_seconds=1800,
        )
