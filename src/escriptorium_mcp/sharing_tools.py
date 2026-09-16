"""Scoped additive access grants using native project and document actions."""

import json
from typing import assert_never

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.group_scope import read_group
from escriptorium_mcp.record_scope import require_project
from escriptorium_mcp.sharing_models import ShareGroup, ShareTarget, ShareUser
from escriptorium_mcp.strict_tools import strict_tool
from escriptorium_mcp.text_scope import RecordId


async def _grant(route: str, target: ShareTarget) -> JsonValue:
    """Resolve one native recipient and submit one grant without mutation retries."""
    match target:
        case ShareUser(username=username):
            body = json.dumps({"user": username})
        case ShareGroup(group_id=group_id):
            _ = await read_group(group_id)
            body = json.dumps({"group": group_id})
        case _:
            assert_never(target)
    try:
        return await call(
            ApiRequest(method="POST", route=route, body_json=body, single_attempt=True)
        )
    except ToolError as error:
        msg = (
            f"{error} Sharing may already have changed. Inspect the resource's "
            "sharing before retrying; no automatic retry occurred."
        )
        raise ToolError(msg) from None


def build_sharing_tools() -> list[Tool]:
    """Build two native additive sharing actions with strict argument boundaries."""

    async def share_project(project_id: Identifier, target: ShareTarget) -> JsonValue:
        """Add project access for one known username or current member group.

        Existing grants remain. Project access includes current and future
        accessible documents. The server decides permission; no owner-only rule
        is assumed. This API has no revoke, role or expiration option. Return
        native updated metadata after one POST, without a follow-up read.
        """
        _ = await require_project(project_id)
        return await _grant(f"projects/{project_id}/share/", target)

    async def share_document(document_id: Identifier, target: ShareTarget) -> JsonValue:
        """Add document access for one known username or current member group.

        Existing grants remain. Other project, group or ownership relationships
        may also grant access. The server decides permission; no owner-only rule
        is assumed. This API has no revoke, role or expiration option. Return
        native updated metadata after one POST, without a follow-up read.
        """
        document = RecordId.model_validate(
            await invoke("GET", f"documents/{document_id}/")
        )
        if document.pk != document_id:
            msg = "The server returned a different document; no writes were sent."
            raise ToolError(msg)
        return await _grant(f"documents/{document_id}/share/", target)

    return [strict_tool(share_project, CHANGE), strict_tool(share_document, CHANGE)]
