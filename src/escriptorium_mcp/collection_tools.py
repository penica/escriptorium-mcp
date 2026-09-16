"""Native collection CRUD with explicit full membership replacement."""

import json
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.collection_models import CollectionCreate, CollectionPatch
from escriptorium_mcp.collection_scope import (
    read_collection,
    read_collection_items,
    require_collection_references,
)


def _payload(data: CollectionCreate | CollectionPatch) -> str:
    """Map public members to native fields without sending document context."""
    body: dict[str, JsonValue] = {}
    if data.name is not None:
        body["name"] = data.name
    if data.default_transcriptions is not None:
        body["default_transcriptions"] = dict(data.default_transcriptions)
    if data.items is not None:
        body["items_to_save"] = [
            {
                "document_part": item.page_id,
                "transcription_layer": item.transcription_id,
            }
            for item in data.items
        ]
    return json.dumps(body)


async def _write(
    method: Literal["POST", "PATCH", "DELETE"], route: str, body_json: str = "{}"
) -> JsonValue:
    """Send one mutation and retain uncertainty about non-atomic native effects."""
    try:
        return await call(ApiRequest(method=method, route=route, body_json=body_json))
    except ToolError as error:
        msg = (
            f"{error} Collection changes may already have been partly applied. "
            "Inspect collections and membership before retrying; "
            "no automatic retry occurred."
        )
        raise ToolError(msg) from None


def register_collections(server: MCPServer) -> None:
    """Register owned collections and explicit complete membership replacement."""

    @server.tool(annotations=READ)
    async def list_collections() -> JsonValue:
        """List all collections owned by the current user, with full pagination."""
        return await call(
            ApiRequest(
                method="GET",
                route="collections/",
                paginate=True,
                strict_pagination=True,
            )
        )

    @server.tool(annotations=READ)
    async def get_collection(collection_id: Identifier) -> JsonValue:
        """Read owned collection metadata; default layers are not membership."""
        return await read_collection(collection_id)

    @server.tool(annotations=CREATE)
    async def create_collection(data: CollectionCreate) -> JsonValue:
        """Create an owned collection and optionally its initial page/layer pairs.

        Default transcriptions are UI selections and do not add/change members.
        The native operation is not atomic: failure may leave partial records.
        """
        await require_collection_references(data.items, data.default_transcriptions)
        return await _write("POST", "collections/", _payload(data))

    @server.tool(annotations=CHANGE)
    async def update_collection(
        collection_id: Identifier, changes: CollectionPatch
    ) -> JsonValue:
        """Update metadata or replace all page/layer pairs in one native PATCH.

        Omitted items preserve membership; [] clears it. Default-layer changes
        do not alter members. Changes can affect already queued training because
        workers read membership at execution. No snapshot, lock or atomicity is
        provided; failure may leave partial changes. Do not automatically retry.
        """
        _ = await read_collection(collection_id)
        await require_collection_references(
            changes.items, changes.default_transcriptions
        )
        return await _write("PATCH", f"collections/{collection_id}/", _payload(changes))

    @server.tool(annotations=DELETE)
    async def delete_collection(collection_id: Identifier) -> JsonValue:
        """Delete the collection and links, preserving source pages, text and models.

        Deletion can remove task-group history and make queued training fail;
        it does not cancel jobs. Check uncertain failures before retrying.
        """
        _ = await read_collection(collection_id)
        return await _write("DELETE", f"collections/{collection_id}/")

    @server.tool(annotations=READ)
    async def list_collection_items(collection_id: Identifier) -> JsonValue:
        """Read all current page/layer pairs, preserving native item metadata."""
        return await read_collection_items(collection_id)
