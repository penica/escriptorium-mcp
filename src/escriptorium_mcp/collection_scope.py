"""Owned collection reads and current document/page/layer access checks."""

from typing import ClassVar

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, JsonValue

from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.collection_models import CollectionMember, DefaultTranscriptions
from escriptorium_mcp.text_scope import RecordId


class CollectionIdentity(BaseModel):
    """Parse the native id without discarding fields from returned JSON."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    id: Identifier


async def read_collection(collection_id: Identifier) -> JsonValue:
    """Read an owned collection and verify its native id, preserving raw metadata."""
    value = await invoke("GET", f"collections/{collection_id}/")
    if CollectionIdentity.model_validate(value).id != collection_id:
        msg = "The server returned a different collection; no writes were sent."
        raise ToolError(msg)
    return value


async def read_collection_items(collection_id: Identifier) -> JsonValue:
    """Read every membership page with strict same-collection pagination checks."""
    _ = await read_collection(collection_id)
    return await call(
        ApiRequest(
            method="GET",
            route=f"collections/{collection_id}/items/",
            paginate=True,
            strict_pagination=True,
        )
    )


async def _require_identity(route: str, expected: Identifier) -> None:
    """Verify a reference using its scoped route and strict returned identity."""
    record = RecordId.model_validate(await invoke("GET", route))
    if record.pk != expected:
        msg = "A source document, page or layer identity differs; no writes were sent."
        raise ToolError(msg)


async def require_collection_references(
    items: list[CollectionMember] | None,
    default_transcriptions: DefaultTranscriptions | None,
) -> None:
    """Recheck current readable sources, without bypassing archived records.

    A layer explicitly returned by its scoped endpoint may be archived. Hidden
    layers fail normally. These reads do not freeze later membership/access.
    """
    members = items or []
    defaults = default_transcriptions or {}
    document_ids = {item.document_id for item in members} | {
        int(key) for key in defaults
    }
    pages = {(item.document_id, item.page_id) for item in members}
    layers = {(item.document_id, item.transcription_id) for item in members} | {
        (int(key), layer_id) for key, layer_id in defaults.items()
    }
    for document_id in sorted(document_ids):
        await _require_identity(f"documents/{document_id}/", document_id)
    for document_id, page_id in sorted(pages):
        await _require_identity(f"documents/{document_id}/parts/{page_id}/", page_id)
    for document_id, layer_id in sorted(layers):
        await _require_identity(
            f"documents/{document_id}/transcriptions/{layer_id}/", layer_id
        )
