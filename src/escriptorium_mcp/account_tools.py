"""Native self/staff account reads and explicitly scoped account mutations."""

from typing import Final

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from pydantic import JsonValue

from escriptorium_mcp.account_models import DirectorySearch, UserCreate, UserPatch
from escriptorium_mcp.account_scope import (
    read_current_user,
    read_user,
    require_staff_account,
)
from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.directory_reads import read_directory
from escriptorium_mcp.strict_tools import strict_tool

USER_SEARCH_FIELDS: Final = ("username", "first_name", "last_name", "email")


async def _mutate(request: ApiRequest) -> JsonValue:
    """Send one account mutation without retrying a possibly committed change."""
    try:
        return await call(request)
    except ToolError as error:
        msg = (
            f"{error} The account may already have changed. "
            "Inspect access and account state before retrying; "
            "no automatic retry occurred."
        )
        raise ToolError(msg) from None


def build_account_tools() -> list[Tool]:
    """Build account tools with strict public top-level argument validation."""

    async def get_current_user() -> JsonValue:
        """Read the authenticated account's native identity and capability fields."""
        return await read_current_user()

    async def list_users(search: DirectorySearch | None = None) -> JsonValue:
        """List visible accounts: self for nonstaff, all native-visible users for staff.

        Optional search is a local case-insensitive substring match of username,
        first/last name or email after full pagination. Its count is local; no
        native search parameters or hidden-user discovery are used.
        """
        return await read_directory("users/", search, USER_SEARCH_FIELDS)

    async def get_user(user_id: Identifier) -> JsonValue:
        """Read an account visible to the current self/staff native queryset."""
        return await read_user(user_id)

    async def create_user(account: UserCreate) -> JsonValue:
        """Create a native account row as staff, preserving omitted defaults.

        Acceptance does not establish a usable password login or send an
        invitation. Password setup, privilege changes and tokens are not fields
        of this operation; native email syntax and uniqueness remain authoritative.
        """
        _ = await require_staff_account()
        return await _mutate(
            ApiRequest(
                method="POST",
                route="users/",
                body_json=account.model_dump_json(exclude_unset=True),
                single_attempt=True,
            )
        )

    async def update_user(user_id: Identifier, changes: UserPatch) -> JsonValue:
        """Edit an account allowed by the native self/staff permissions.

        Own-email changes are permitted, without a verification-email guarantee.
        Self-deactivation may end access; username changes may affect login and
        sharing. Omitted fields remain unchanged; empty display names clear them.
        """
        _ = await read_user(user_id)
        return await _mutate(
            ApiRequest(
                method="PATCH",
                route=f"users/{user_id}/",
                body_json=changes.model_dump_json(exclude_unset=True),
                single_attempt=True,
            )
        )

    async def delete_user(user_id: Identifier) -> JsonValue:
        """Delete an account and native dependent records; staff permission required.

        Self-deletion can end access. Collections, tags and reporting/download
        records may cascade, while owned content may lose its owner. Protected
        relationships can reject deletion; this is not a complete erasure report.
        """
        current = await require_staff_account()
        if current.pk != user_id:
            _ = await read_user(user_id)
        return await _mutate(
            ApiRequest(method="DELETE", route=f"users/{user_id}/", single_attempt=True)
        )

    return [
        strict_tool(get_current_user, READ),
        strict_tool(list_users, READ),
        strict_tool(get_user, READ),
        strict_tool(create_user, CREATE),
        strict_tool(update_user, CHANGE),
        strict_tool(delete_user, DELETE),
    ]
