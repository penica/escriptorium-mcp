"""Scoped tag definition CRUD, separate from project/document assignments."""

from typing import assert_never

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.tag_models import (
    PersonalProjectTags,
    ProjectDocumentTags,
    TagCreate,
    TagIdentity,
    TagPatch,
    TagProjectIdentity,
    TagTarget,
)


async def tag_route(target: TagTarget) -> str:
    """Derive a fixed route after checking any requested parent project identity."""
    match target:
        case PersonalProjectTags():
            route = "tags/project/"
        case ProjectDocumentTags(project_id=project_id):
            project = TagProjectIdentity.model_validate(
                await invoke("GET", f"projects/{project_id}/")
            )
            if project.id != project_id:
                msg = "The server returned a different project; no writes were sent."
                raise ToolError(msg)
            route = f"projects/{project_id}/tags/"
        case _:
            assert_never(target)
    return route


async def read_tag(route: str, tag_id: Identifier) -> JsonValue:
    """Confirm nested tag identity before returning metadata or changing a row."""
    raw = await invoke("GET", f"{route}{tag_id}/")
    if TagIdentity.model_validate(raw).pk != tag_id:
        msg = "The server returned a different tag; no writes were sent."
        raise ToolError(msg)
    return raw


def register_tags(server: MCPServer) -> None:
    """Expose tag definitions within current-user or explicitly selected projects."""

    @server.tool(annotations=READ)
    async def list_tags(target: TagTarget) -> JsonValue:
        """List every tag definition in one scope, preserving native pagination data.

        personal_projects selects the current user's tags for projects.
        project_documents selects tags for documents in the specified project.
        These are definitions, not a list of assignments to individual records.
        """
        return await call(
            ApiRequest(method="GET", route=await tag_route(target), paginate=True)
        )

    @server.tool(annotations=READ)
    async def get_tag(target: TagTarget, tag_id: Identifier) -> JsonValue:
        """Read one tag definition within its personal or project scope."""
        return await read_tag(await tag_route(target), tag_id)

    @server.tool(annotations=CREATE)
    async def create_tag(target: TagTarget, data: TagCreate) -> JsonValue:
        """Create a tag definition for personal projects or one project's documents.

        Omit color for the server default. Color is nonblank and at most seven
        characters; server validation remains authoritative. Creation does not
        assign the tag to any record. Conflicting names remain native errors.
        """
        return await invoke("POST", await tag_route(target), data)

    @server.tool(annotations=CHANGE)
    async def update_tag(
        target: TagTarget, tag_id: Identifier, changes: TagPatch
    ) -> JsonValue:
        """Rename or recolor a definition everywhere it is assigned in its scope.

        Omit unchanged fields; null and empty patches are unsupported. This does
        not relabel a single project's or document's assignment independently.
        Preflight reads do not lock the row; native permission errors propagate.
        """
        route = await tag_route(target)
        _ = await read_tag(route, tag_id)
        return await invoke("PATCH", f"{route}{tag_id}/", changes)

    @server.tool(annotations=DELETE)
    async def delete_tag(target: TagTarget, tag_id: Identifier) -> JsonValue:
        """Delete a definition and unassign it from every record in that scope.

        Projects, documents and their content remain. To unassign only one record,
        replace that record's tag array instead. Native 204 means success; this
        operation is not automatically retried or followed by a speculative read.
        """
        route = await tag_route(target)
        _ = await read_tag(route, tag_id)
        return await invoke("DELETE", f"{route}{tag_id}/")
