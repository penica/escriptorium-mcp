"""Owner-scoped model mutations, association reads and checkpoint transfers."""

from pathlib import Path

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import FilePath, HttpUrl, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.file_models import ExportDownload
from escriptorium_mcp.model_files import model_file_url
from escriptorium_mcp.model_models import (
    ModelRecord,
    ModelUpdate,
    ReplacementMetadata,
    Revision,
)
from escriptorium_mcp.settings import load_settings


async def read_model(model_id: Identifier) -> ModelRecord:
    """Read permission and storage evidence through the authenticated adapter."""
    return ModelRecord.model_validate(await invoke("GET", f"models/{model_id}/"))


async def require_owned_model(model_id: Identifier, *, idle: bool = False) -> None:
    """Enforce ownership separately from the upstream readable-model queryset."""
    model = await read_model(model_id)
    if model.rights != "owner":
        message = (
            "Only the model owner can update, replace or delete it through this MCP."
        )
        raise ToolError(message)
    if idle and model.training is not False:
        message = "Stop training before changing model weights/job/size or deleting it."
        raise ToolError(message)


def register_models(server: MCPServer) -> None:
    """Add model operations without inventing writable document associations."""

    @server.tool(annotations=CHANGE)
    async def update_model(model_id: Identifier, changes: ModelUpdate) -> JsonValue:
        """Rename or update an owned model's job type/storage-size metadata.

        job is 1 for segmentation or 2 for recognition. Omit unchanged fields;
        nulls and document association edits are unsupported. Job/size edits
        require stopped training. Changing job metadata does not convert weights.
        file_size is storage accounting; file replacement calculates it for you.
        """
        await require_owned_model(
            model_id, idle=bool(changes.model_fields_set - {"name"})
        )
        return await invoke("PATCH", f"models/{model_id}/", changes)

    @server.tool(annotations=CHANGE)
    async def replace_model_file(
        model_id: Identifier, file_path: FilePath
    ) -> JsonValue:
        """Replace an owned, idle model's weights from a local MCP-host file.

        Replaces the current file reference and size; this does not create a
        checkpoint backup. Download the current file first if it must be retained.
        Server file validation and permissions still apply.
        """
        await require_owned_model(model_id, idle=True)
        return await call(
            ApiRequest(
                method="PATCH",
                route=f"models/{model_id}/",
                file_path=file_path,
                file_field="file",
                body_json=ReplacementMetadata(
                    file_size=(await anyio.Path(file_path).stat()).st_size
                ).model_dump_json(),
            ),
            timeout_seconds=1800,
        )

    @server.tool(annotations=DELETE)
    async def delete_model(model_id: Identifier) -> JsonValue:
        """Delete an owned, idle model and its server-managed relationships.

        This does not delete document transcriptions. Download files/checkpoints
        to retain them; upstream may remove stored model files when deleting.
        """
        await require_owned_model(model_id, idle=True)
        return await invoke("DELETE", f"models/{model_id}/")

    @server.tool(annotations=READ)
    async def list_model_versions(model_id: Identifier) -> JsonValue:
        """List advertised checkpoints with revision IDs and available training metrics.

        File references do not prove bytes still exist. Use download_model with
        a revision to retrieve one; no checkpoint revert/delete REST action exists.
        """
        model = await read_model(model_id)
        return {
            "model_id": model_id,
            "current_file": model.file,
            "versions": [version.as_json() for version in model.versions],
        }

    @server.tool(annotations=READ)
    async def get_model_documents(model_id: Identifier) -> JsonValue:
        """Read document associations; the audited REST API cannot bind/unbind them.

        Segmentation, transcription and training create associations as a side
        effect. Do not submit a processing job solely to edit this relationship.
        """
        model = await read_model(model_id)
        return {
            "model_id": model_id,
            "document_ids": list[JsonValue](model.documents),
            "associations_editable": False,
            "details": (
                "Associations are read-only in the model REST serializer. "
                "Use the eScriptorium UI to unbind."
            ),
        }

    @server.tool(annotations=CREATE)
    async def download_model(
        model_id: Identifier, destination: Path, revision: Revision | None = None
    ) -> JsonValue:
        """Save current model weights or one advertised checkpoint on the MCP host.

        Omit revision for the current file. Destination and .part must be new and
        outside the scan-only Books archive. Return byte count/SHA-256 only after
        transfer completion. Missing files remain errors; redirects are refused.
        """
        model = await read_model(model_id)
        url = model_file_url(model, str(load_settings().url), revision)
        return await call(
            ExportDownload(url=HttpUrl(url), destination=destination),
            timeout_seconds=1800,
        )
