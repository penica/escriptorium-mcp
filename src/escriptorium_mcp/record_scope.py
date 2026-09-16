"""Conditional tag assignment scope checks before native record mutations."""

from typing import ClassVar

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.text_scope import RecordId, collection


class ProjectIdentity(BaseModel):
    """Projects use id, unlike document and tag pk fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    id: Identifier
    slug: str | None = None


class DocumentProject(RecordId):
    """Read only identity and the current project for tag replacement."""

    project_id: Identifier | None = None
    project: str | None = None


async def require_project(project_id: Identifier) -> ProjectIdentity:
    """Verify the requested project identity without asserting write permission."""
    project = ProjectIdentity.model_validate(
        await invoke("GET", f"projects/{project_id}/")
    )
    if project.id != project_id:
        msg = "The server returned a different project; no writes were sent."
        raise ToolError(msg)
    return project


async def project_for_slug(slug: str) -> ProjectIdentity:
    """Resolve the write-side slug through the complete readable collection."""
    matches = [
        project
        for row in await collection("projects/")
        if (project := ProjectIdentity.model_validate(row)).slug == slug
    ]
    if len(matches) != 1:
        msg = "The target project slug did not resolve uniquely; no writes were sent."
        raise ToolError(msg)
    project = await require_project(matches[0].id)
    if project.slug != slug:
        msg = "The target project slug changed; no writes were sent."
        raise ToolError(msg)
    return project


async def require_tags(route: str, tags: list[Identifier]) -> None:
    """Check the full allowed collection, including IDs beyond its first page."""
    known = {RecordId.model_validate(row).pk for row in await collection(route)}
    if not set(tags).issubset(known):
        msg = "A tag is outside the target scope; no writes were sent."
        raise ToolError(msg)


async def require_personal_tags(tags: list[Identifier]) -> None:
    """Project assignments may use only the authenticated user's tag definitions."""
    await require_tags("tags/project/", tags)


async def require_document_tags(
    tags: list[Identifier],
    project_slug: str | None,
    document_id: Identifier | None = None,
) -> None:
    """Resolve the effective project, including a simultaneous document move.

    These reads are preflight checks, not a lock or permission to retry writes.
    """
    document: DocumentProject | None = None
    if document_id is not None:
        document = DocumentProject.model_validate(
            await invoke("GET", f"documents/{document_id}/")
        )
        if document.pk != document_id:
            msg = "The server returned a different document; no writes were sent."
            raise ToolError(msg)
    if project_slug is not None:
        project = await project_for_slug(project_slug)
    elif document is not None and document.project_id is not None:
        project = await require_project(document.project_id)
    elif document is not None and document.project is not None:
        project = await project_for_slug(document.project)
    else:
        msg = "Cannot determine the document's project; no writes were sent."
        raise ToolError(msg)
    await require_tags(f"projects/{project.id}/tags/", tags)
