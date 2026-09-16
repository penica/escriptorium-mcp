"""Typed eScriptorium tools shared by both MCP transports."""

from typing import Final

from mcp.server import MCPServer
from mcp_types import ToolAnnotations
from pydantic import JsonValue

from escriptorium_mcp.account_tools import build_account_tools
from escriptorium_mcp.alignment_tools import register_alignment
from escriptorium_mcp.annotation_tools import register_annotations
from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, Name, Request, call
from escriptorium_mcp.collection_tools import register_collections
from escriptorium_mcp.collection_training import register_collection_training
from escriptorium_mcp.download_tools import register_downloads
from escriptorium_mcp.file_tools import register_files
from escriptorium_mcp.font_tools import build_font_tools
from escriptorium_mcp.group_tools import build_group_tools
from escriptorium_mcp.import_tools import register_imports
from escriptorium_mcp.instance_tools import register_instances
from escriptorium_mcp.job_tools import register_jobs
from escriptorium_mcp.metadata_tools import register_metadata
from escriptorium_mcp.model_tools import register_models
from escriptorium_mcp.ontology_native import register_native
from escriptorium_mcp.ontology_repair import register_repairs
from escriptorium_mcp.ontology_restore import register_snapshots
from escriptorium_mcp.ontology_tools import register_ontology
from escriptorium_mcp.page_models import PageFilters
from escriptorium_mcp.page_tools import list_filtered_pages, register_page_operations
from escriptorium_mcp.project_models import ProjectCreateSettings, RecordName
from escriptorium_mcp.record_operations import (
    create_project_record,
    list_document_records,
    list_project_records,
    register_record_expansion,
)
from escriptorium_mcp.record_query_models import DocumentFilters, ProjectFilters
from escriptorium_mcp.record_tools import register_records
from escriptorium_mcp.segmentation import register_segmentation
from escriptorium_mcp.segmentation_bulk import register_segmentation_expansion
from escriptorium_mcp.sharing_tools import build_sharing_tools
from escriptorium_mcp.tag_tools import register_tags
from escriptorium_mcp.task_tools import register_task_monitoring
from escriptorium_mcp.taxonomy_edit import register_taxonomy_edits
from escriptorium_mcp.taxonomy_merge import register_taxonomy_merges
from escriptorium_mcp.text_bulk import register_text_bulk
from escriptorium_mcp.text_reads import register_text_reads
from escriptorium_mcp.text_tools import register_text
from escriptorium_mcp.training_tools import register_training
from escriptorium_mcp.witness_tools import register_witnesses

READ: Final = ToolAnnotations(read_only_hint=True, destructive_hint=False)
WRITE: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False
)


def create_server() -> MCPServer:
    """Build tools without making network calls or requiring credentials."""
    server = MCPServer(
        "eScriptorium",
        version="1.0.0",
        tools=(
            build_account_tools()
            + build_group_tools()
            + build_sharing_tools()
            + build_font_tools()
        ),
        instructions=(
            "Use server primary keys, not page numbers. "
            "Write and processing tools change the remote instance. "
            "Queued jobs are not completed jobs. Record download, visual inspection "
            "and transcription completion separately."
        ),
    )

    @server.tool(annotations=READ)
    async def list_projects(filters: ProjectFilters | None = None) -> JsonValue:
        """List accessible projects with native name/tag filters and ordering.

        Follows pagination and preserves expanded sharing, tags and new fields.
        Native OR tag queries can return duplicate rows; counts are not rewritten.
        """
        return await list_project_records(filters)

    @server.tool(annotations=READ)
    async def get_project(project_id: Identifier) -> JsonValue:
        """Read project metadata by primary key."""
        return await invoke("GET", f"projects/{project_id}/")

    @server.tool(annotations=READ)
    async def list_documents(filters: DocumentFilters | None = None) -> JsonValue:
        """List accessible documents, preserving all native fields and pagination.

        Optional project filter is a numeric ID; document create/move uses a slug.
        Supports name/tag filters and ordering without deduplicating native rows.
        """
        return await list_document_records(filters)

    @server.tool(annotations=READ)
    async def get_document(document_id: Identifier) -> JsonValue:
        """Read document metadata and its available transcription layers."""
        return await invoke("GET", f"documents/{document_id}/")

    @server.tool(annotations=READ)
    async def list_pages(
        document_id: Identifier, filters: PageFilters | None = None
    ) -> JsonValue:
        """List pages, optionally filtering names/filenames and sorting server-side."""
        if filters is not None:
            return await list_filtered_pages(document_id, filters)
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
        transcription_id: Identifier | None = None,
    ) -> JsonValue:
        """Read page text/confidence/history, optionally filtered to one layer."""
        if transcription_id is not None:
            _ = await invoke(
                "GET", f"documents/{document_id}/transcriptions/{transcription_id}/"
            )
            return await call(
                ApiRequest(
                    method="GET",
                    route=f"documents/{document_id}/parts/{page_id}/transcriptions/",
                    query={"transcription": str(transcription_id)},
                    paginate=True,
                )
            )
        return await call(
            Request(
                operation="get_page_transcriptions",
                document_id=document_id,
                page_id=page_id,
            )
        )

    @server.tool(annotations=WRITE)
    async def create_project(
        name: RecordName, settings: ProjectCreateSettings | None = None
    ) -> JsonValue:
        """Create a project with optional guidelines, personal tags and display font.

        Existing name-only calls remain valid. Repetition may create duplicates.
        Omitted settings retain native defaults; supplied tag arrays are complete.
        """
        return await create_project_record(name, settings)

    @server.tool(annotations=WRITE)
    async def create_transcription(document_id: Identifier, name: Name) -> JsonValue:
        """Create an empty transcription layer in an existing document."""
        return await call(
            Request(
                operation="create_transcription", document_id=document_id, name=name
            )
        )

    _register_extensions(server)
    return server


def _register_extensions(server: MCPServer) -> None:
    for register in (
        register_records,
        register_record_expansion,
        register_metadata,
        register_tags,
        register_collections,
        register_collection_training,
        register_alignment,
        register_witnesses,
        register_page_operations,
        register_text,
        register_text_bulk,
        register_text_reads,
        register_segmentation,
        register_segmentation_expansion,
        register_jobs,
        register_models,
        register_task_monitoring,
        register_training,
        register_files,
        register_downloads,
        register_imports,
        register_ontology,
        register_annotations,
        register_instances,
        register_taxonomy_edits,
        register_taxonomy_merges,
        register_repairs,
        register_native,
        register_snapshots,
    ):
        register(server)
