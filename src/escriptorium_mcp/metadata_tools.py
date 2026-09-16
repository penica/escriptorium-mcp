"""Metadata association CRUD with explicit global shared-key mutation."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, JOB, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.metadata_models import (
    MetadataCreate,
    MetadataTarget,
    MetadataValuePatch,
    SharedMetadataKeyPatch,
    SharedMetadataKeyUpdate,
)
from escriptorium_mcp.metadata_scope import metadata_route, read_metadata


def register_metadata(server: MCPServer) -> None:
    """Register both document and page metadata through the same scoped surface."""

    @server.tool(annotations=READ)
    async def list_metadata(target: MetadataTarget) -> JsonValue:
        """List every metadata association for one document or page.

        Follow all pagination and preserve duplicate rows and native fields.
        This lists associations, not all global key definitions or references.
        """
        route = await metadata_route(target)
        return await call(ApiRequest(method="GET", route=route, paginate=True))

    @server.tool(annotations=READ)
    async def get_metadata(
        target: MetadataTarget, metadata_id: Identifier
    ) -> JsonValue:
        """Read one metadata association within the specified document or page."""
        return await read_metadata(await metadata_route(target), metadata_id)

    @server.tool(annotations=CREATE)
    async def create_metadata(
        target: MetadataTarget, data: MetadataCreate
    ) -> JsonValue:
        """Create a metadata association with a nested shared key name and value.

        Repeated creation can create duplicate association rows. A key name already
        used with a different CIDOC identifier can fail rather than merge. Omit
        cidoc_id to leave it unspecified; explicit null or blank are native values.
        This is not an upsert and no automatic retry is performed.
        """
        return await invoke("POST", await metadata_route(target), data)

    @server.tool(annotations=CHANGE)
    async def update_metadata(
        target: MetadataTarget,
        metadata_id: Identifier,
        changes: MetadataValuePatch,
    ) -> JsonValue:
        """Replace only this association's value; its shared key is unchanged."""
        route = await metadata_route(target)
        _ = await read_metadata(route, metadata_id)
        return await invoke("PATCH", f"{route}{metadata_id}/", changes)

    @server.tool(annotations=JOB)
    async def update_shared_metadata_key(
        target: MetadataTarget,
        metadata_id: Identifier,
        changes: SharedMetadataKeyPatch,
    ) -> JsonValue:
        """Edit the GLOBAL shared key used by this metadata association.

        Renaming or changing CIDOC affects every document/page using that key,
        including unrelated records. The API cannot enumerate all references.
        This is not local relabeling or rebinding. Native updates are not atomic;
        uniqueness failures can occur. This tool sends only nested key changes,
        never a value change in the same request, and never automatically retries.
        """
        route = await metadata_route(target)
        _ = await read_metadata(route, metadata_id)
        return await invoke(
            "PATCH", f"{route}{metadata_id}/", SharedMetadataKeyUpdate(key=changes)
        )

    @server.tool(annotations=DELETE)
    async def delete_metadata(
        target: MetadataTarget, metadata_id: Identifier
    ) -> JsonValue:
        """Delete only this document/page metadata association.

        The global key, other associations and document/page content remain.
        Native bodyless 204 success is returned without a follow-up read.
        """
        route = await metadata_route(target)
        _ = await read_metadata(route, metadata_id)
        return await invoke("DELETE", f"{route}{metadata_id}/")
