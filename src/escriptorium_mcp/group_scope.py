"""Member-scoped group identity checks without a false owner-only restriction."""

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.text_scope import RecordId


async def read_group(group_id: Identifier) -> JsonValue:
    """Read native membership-visible detail and preserve all returned metadata."""
    record = await invoke("GET", f"groups/{group_id}/")
    if RecordId.model_validate(record).pk != group_id:
        msg = "The server returned a different group; no writes were sent."
        raise ToolError(msg)
    return record
