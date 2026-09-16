"""Document, page and association identity checks before metadata access."""

from typing import assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.metadata_models import (
    DocumentMetadataTarget,
    MetadataTarget,
    PageMetadataTarget,
)
from escriptorium_mcp.text_scope import RecordId, require_page


async def metadata_route(target: MetadataTarget) -> str:
    """Authorize the requested parents before using their nested metadata route."""
    document_route = f"documents/{target.document_id}/"
    document = RecordId.model_validate(await invoke("GET", document_route))
    if document.pk != target.document_id:
        msg = "The server returned a different metadata document."
        raise ToolError(msg)
    match target:
        case DocumentMetadataTarget():
            return document_route + "metadata/"
        case PageMetadataTarget():
            return (
                await require_page(target.document_id, target.page_id)
            ) + "metadata/"
        case _:
            assert_never(target)


async def read_metadata(route: str, metadata_id: Identifier) -> JsonValue:
    """Verify a scoped row's identity without dropping unknown native fields."""
    result = await invoke("GET", f"{route}{metadata_id}/")
    if RecordId.model_validate(result).pk != metadata_id:
        msg = "The server returned a different metadata association."
        raise ToolError(msg)
    return result
