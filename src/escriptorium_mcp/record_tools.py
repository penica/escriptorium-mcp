"""MCP document and page management operations."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, Name, call
from escriptorium_mcp.record_models import (
    DocumentCreate,
    DocumentPatch,
    PageMetadata,
    PagePatch,
    PageUpload,
    Rename,
)


def register_records(server: MCPServer) -> None:
    """Register record creation, metadata changes and deletion."""

    @server.tool(annotations=READ)
    async def list_scripts() -> JsonValue:
        """List writing systems; use their name in create_document.main_script."""
        return await call(ApiRequest(method="GET", route="scripts/", paginate=True))

    @server.tool(annotations=CREATE)
    async def create_document(data: DocumentCreate) -> JsonValue:
        """Create an empty document; project is a slug, main_script a script name."""
        return await invoke("POST", "documents/", data)

    @server.tool(annotations=CHANGE)
    async def update_document(
        document_id: Identifier, changes: DocumentPatch
    ) -> JsonValue:
        """Rename a document, move it to another project slug, or change metadata."""
        return await invoke("PATCH", f"documents/{document_id}/", changes)

    @server.tool(annotations=CHANGE)
    async def rename_project(project_id: Identifier, name: Name) -> JsonValue:
        """Rename a project while preserving its sharing settings."""
        return await invoke("PATCH", f"projects/{project_id}/", Rename(name=name))

    @server.tool(annotations=CREATE)
    async def upload_page(document_id: Identifier, image: PageUpload) -> JsonValue:
        """Upload one local image into a document; conversion may run asynchronously."""
        metadata = PageMetadata(name=image.name, source=image.source)
        return await call(
            ApiRequest(
                method="POST",
                route=f"documents/{document_id}/parts/",
                file_path=image.image_path,
                body_json=metadata.model_dump_json(),
            ),
            timeout_seconds=1800,
        )

    @server.tool(annotations=CHANGE)
    async def update_page(
        document_id: Identifier,
        page_id: Identifier,
        changes: PagePatch,
    ) -> JsonValue:
        """Rename a page or edit its source, comments and typology."""
        return await invoke(
            "PATCH", f"documents/{document_id}/parts/{page_id}/", changes
        )

    @server.tool(annotations=DELETE)
    async def delete_document(document_id: Identifier) -> JsonValue:
        """Permanently delete a document, its pages and transcriptions."""
        return await invoke("DELETE", f"documents/{document_id}/")

    @server.tool(annotations=DELETE)
    async def delete_project(project_id: Identifier) -> JsonValue:
        """Delete a project; its documents may also be removed by the server."""
        return await invoke("DELETE", f"projects/{project_id}/")

    @server.tool(annotations=DELETE)
    async def delete_page(document_id: Identifier, page_id: Identifier) -> JsonValue:
        """Delete a page and its segmentation and transcriptions."""
        return await invoke("DELETE", f"documents/{document_id}/parts/{page_id}/")
