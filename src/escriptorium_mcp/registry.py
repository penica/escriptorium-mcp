"""Typed eScriptorium tools shared by both MCP transports."""

from typing import Final

from mcp.server import MCPServer
from mcp_types import ToolAnnotations
from pydantic import JsonValue

from escriptorium_mcp.annotation_tools import register_annotations
from escriptorium_mcp.bridge import Identifier, Name, Request, call
from escriptorium_mcp.file_tools import register_files
from escriptorium_mcp.instance_tools import register_instances
from escriptorium_mcp.job_tools import register_jobs
from escriptorium_mcp.model_tools import register_models
from escriptorium_mcp.ontology_native import register_native
from escriptorium_mcp.ontology_repair import register_repairs
from escriptorium_mcp.ontology_restore import register_snapshots
from escriptorium_mcp.ontology_tools import register_ontology
from escriptorium_mcp.record_tools import register_records
from escriptorium_mcp.segmentation import register_segmentation
from escriptorium_mcp.task_tools import register_task_monitoring
from escriptorium_mcp.taxonomy_edit import register_taxonomy_edits
from escriptorium_mcp.taxonomy_merge import register_taxonomy_merges
from escriptorium_mcp.text_tools import register_text

READ: Final = ToolAnnotations(read_only_hint=True, destructive_hint=False)
WRITE: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False
)


def create_server() -> MCPServer:
    """Build tools without making network calls or requiring credentials."""
    server = MCPServer(
        "eScriptorium",
        version="0.7.0",
        instructions=(
            "Use server primary keys, not page numbers. "
            "Write and processing tools change the remote instance. "
            "Queued jobs are not completed jobs. Record download, visual inspection "
            "and transcription completion separately."
        ),
    )

    @server.tool(annotations=READ)
    async def list_projects() -> JsonValue:
        """List all accessible projects; follows the connector's pagination."""
        return await call(Request(operation="list_projects"))

    @server.tool(annotations=READ)
    async def get_project(project_id: Identifier) -> JsonValue:
        """Read project metadata by primary key."""
        return await call(Request(operation="get_project", project_id=project_id))

    @server.tool(annotations=READ)
    async def list_documents() -> JsonValue:
        """List all accessible documents; follows the connector's pagination."""
        return await call(Request(operation="list_documents"))

    @server.tool(annotations=READ)
    async def get_document(document_id: Identifier) -> JsonValue:
        """Read document metadata and its available transcription layers."""
        return await call(Request(operation="get_document", document_id=document_id))

    @server.tool(annotations=READ)
    async def list_pages(document_id: Identifier) -> JsonValue:
        """List available scanned parts of a document."""
        return await call(Request(operation="list_pages", document_id=document_id))

    @server.tool(annotations=READ)
    async def get_page(document_id: Identifier, page_id: Identifier) -> JsonValue:
        """Read a page's metadata, image references and processing state."""
        return await call(
            Request(operation="get_page", document_id=document_id, page_id=page_id)
        )

    @server.tool(annotations=READ)
    async def list_lines(document_id: Identifier, page_id: Identifier) -> JsonValue:
        """Read segmented lines for a page."""
        return await call(
            Request(operation="list_lines", document_id=document_id, page_id=page_id)
        )

    @server.tool(annotations=READ)
    async def list_regions(document_id: Identifier, page_id: Identifier) -> JsonValue:
        """Read segmented regions for a page."""
        return await call(
            Request(operation="list_regions", document_id=document_id, page_id=page_id)
        )

    @server.tool(annotations=READ)
    async def list_transcriptions(document_id: Identifier) -> JsonValue:
        """List transcription layers and their primary keys."""
        return await call(
            Request(operation="list_transcriptions", document_id=document_id)
        )

    @server.tool(annotations=READ)
    async def get_page_transcriptions(
        document_id: Identifier,
        page_id: Identifier,
    ) -> JsonValue:
        """Read line text, layer IDs, confidence and revision metadata for a page."""
        return await call(
            Request(
                operation="get_page_transcriptions",
                document_id=document_id,
                page_id=page_id,
            )
        )

    @server.tool(annotations=WRITE)
    async def create_project(name: Name) -> JsonValue:
        """Create a remote project. Repeating this call may create duplicates."""
        return await call(Request(operation="create_project", name=name))

    @server.tool(annotations=WRITE)
    async def create_transcription(document_id: Identifier, name: Name) -> JsonValue:
        """Create an empty transcription layer in an existing document."""
        return await call(
            Request(
                operation="create_transcription", document_id=document_id, name=name
            )
        )

    register_records(server)
    register_text(server)
    register_segmentation(server)
    register_jobs(server)
    register_models(server)
    register_task_monitoring(server)
    register_files(server)
    register_ontology(server)
    register_annotations(server)
    register_instances(server)
    register_taxonomy_edits(server)
    register_taxonomy_merges(server)
    register_repairs(server)
    register_native(server)
    register_snapshots(server)
    return server
