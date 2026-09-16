"""Current-account capability and native visible-user identity checks."""

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, StrictBool

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.text_scope import RecordId


class StaffAccount(RecordId):
    """Parse the exact native permission used for account creation/deletion."""

    is_staff: StrictBool


async def read_current_user() -> JsonValue:
    """Retain native current-account metadata after strict positive-pk validation."""
    value = await invoke("GET", "users/current/")
    _ = RecordId.model_validate(value)
    return value


async def read_user(user_id: Identifier) -> JsonValue:
    """Read a self/staff-visible account and verify its requested native pk."""
    value = await invoke("GET", f"users/{user_id}/")
    if RecordId.model_validate(value).pk != user_id:
        msg = "The server returned a different account; no writes were sent."
        raise ToolError(msg)
    return value


async def require_staff_account() -> StaffAccount:
    """Use is_staff, not invitation capability, as native POST/DELETE authority."""
    current = StaffAccount.model_validate(await read_current_user())
    if not current.is_staff:
        msg = "Native account creation and deletion require a staff account."
        raise ToolError(msg)
    return current
