"""Native member-group operations with explicit group creation uncertainty."""

from mcp.server.mcpserver.tools import Tool
from pydantic import JsonValue

from escriptorium_mcp.account_models import DirectorySearch
from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.directory_reads import read_directory
from escriptorium_mcp.group_creation import submit_group
from escriptorium_mcp.group_models import (
    GroupName,
    GroupNameBody,
    NativeCreateAcknowledgment,
)
from escriptorium_mcp.group_scope import read_group
from escriptorium_mcp.strict_tools import strict_tool


def build_group_tools() -> list[Tool]:
    """Build member-group tools that reject unknown top-level request arguments."""

    async def list_groups(search: DirectorySearch | None = None) -> JsonValue:
        """List all groups visible through current membership, including for staff.

        Optional case-insensitive name search runs locally after full pagination.
        Its count is the local match count; no native search parameter is sent.
        With no search, preserve the native collection shape and metadata.
        """
        return await read_directory("groups/", search, ("name",))

    async def get_group(group_id: Identifier) -> JsonValue:
        """Read a membership-visible group; staff has no arbitrary-group bypass."""
        return await read_group(group_id)

    async def create_group(
        name: GroupName,
        acknowledge_native_create_limitations: NativeCreateAcknowledgment,
    ) -> JsonValue:
        """Create a native group, acknowledging possible missing membership/ownership.

        Required acknowledge_native_create_limitations=true accepts that the native
        REST endpoint may leave the creator outside an ownerless, inaccessible group.
        Send one creation request, then at most one bounded detail read. Return native
        acceptance separately from observed readability, membership and ownership;
        failed verification never discards acceptance or implies no group was created.
        No membership repair, owner change, web workflow, cleanup or retry occurs.
        """
        _ = acknowledge_native_create_limitations
        return await submit_group(name)

    async def update_group(group_id: Identifier, name: GroupName) -> JsonValue:
        """Rename one membership-visible group without changing its members or owner.

        Native REST access is member-scoped, not owner-only. Existing sharing
        assignments remain attached to the renamed group. No automatic retry occurs.
        """
        _ = await read_group(group_id)
        return await call(
            ApiRequest(
                method="PATCH",
                route=f"groups/{group_id}/",
                body_json=GroupNameBody(name=name).model_dump_json(),
                single_attempt=True,
            )
        )

    async def delete_group(group_id: Identifier) -> JsonValue:
        """Delete the group and its memberships, sharing links and group model rights.

        Source projects/documents remain, but members may lose access derived from
        this group. This is not removal of one member or one sharing grant. Native
        REST access is member-scoped, including for staff; no owner-only claim is made.
        No automatic retry or speculative read after successful deletion occurs.
        """
        _ = await read_group(group_id)
        return await call(
            ApiRequest(
                method="DELETE", route=f"groups/{group_id}/", single_attempt=True
            )
        )

    return [
        strict_tool(list_groups, READ),
        strict_tool(get_group, READ),
        strict_tool(create_group, CREATE),
        strict_tool(update_group, CHANGE),
        strict_tool(delete_group, DELETE),
    ]
