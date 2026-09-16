"""Native project/document reads and expanded project settings operations."""

from collections.abc import Sequence
from typing import Literal

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.project_models import (
    ProjectCreate,
    ProjectCreateSettings,
    ProjectPatch,
    RecordName,
)
from escriptorium_mcp.record_query_models import (
    DocumentFilters,
    ElementQuery,
    ProjectFilters,
    StatisticsOptions,
)
from escriptorium_mcp.record_scope import require_personal_tags, require_project


def _listing(
    route: Literal["projects/", "documents/"],
    name: str | None,
    tags: str | None,
    ordering: Sequence[str] | None,
    project: Identifier | None = None,
) -> ApiRequest:
    """Serialize only native supported filters while retaining full pagination."""
    query: dict[str, str] = {}
    if name is not None:
        query["name"] = name
    if tags is not None:
        query["tags"] = tags
    if ordering is not None:
        query["ordering"] = ",".join(ordering)
    if project is not None:
        query["project"] = str(project)
    return ApiRequest(method="GET", route=route, query=query, paginate=True)


async def list_project_records(filters: ProjectFilters | None = None) -> JsonValue:
    """Keep raw fields for both no-argument and filtered project lists."""
    options = filters or ProjectFilters()
    return await call(
        _listing("projects/", options.name, options.tags, options.ordering)
    )


async def list_document_records(filters: DocumentFilters | None = None) -> JsonValue:
    """Keep native document fields, counts and duplicate OR-filter matches."""
    options = filters or DocumentFilters()
    return await call(
        _listing(
            "documents/", options.name, options.tags, options.ordering, options.project
        )
    )


async def create_project_record(
    name: RecordName, settings: ProjectCreateSettings | None = None
) -> JsonValue:
    """Preserve the name-only create call while allowing native optional settings."""
    body: dict[str, JsonValue] = {"name": name}
    if settings is not None:
        if "guidelines" in settings.model_fields_set:
            body["guidelines"] = settings.guidelines
        if settings.tags is not None:
            await require_personal_tags(settings.tags)
            body["tags"] = list(settings.tags)
    return await invoke("POST", "projects/", ProjectCreate.model_validate(body))


def register_record_expansion(server: MCPServer) -> None:
    """Register project settings and document aggregate/page-ID native reads."""

    @server.tool(annotations=CHANGE)
    async def update_project(
        project_id: Identifier, changes: ProjectPatch
    ) -> JsonValue:
        """Update project name, guidelines or complete personal-tag assignments.

        Tags replace all assignments; [] clears them. Guidelines accept null or
        blank to clear. Preflight reads do not lock records against other edits.
        """
        if changes.tags is not None:
            _ = await require_project(project_id)
            await require_personal_tags(changes.tags)
        return await invoke("PATCH", f"projects/{project_id}/", changes)

    @server.tool(annotations=READ)
    async def get_document_statistics(
        document_id: Identifier, options: StatisticsOptions | None = None
    ) -> JsonValue:
        """Get native geometry/annotation counts, including untyped entries.

        Defaults may be cached for an hour. refresh=true recomputes; without
        ordering it also updates the default cache. These counts are not
        transcription characters or job progress.
        Ordering by typology applies to geometry, taxonomy to annotations;
        the other category retains native frequency ordering.
        """
        query: dict[str, str] = {}
        if options is not None:
            if options.ordering is not None:
                query["ordering"] = options.ordering
            if "refresh" in options.model_fields_set:
                query["refresh"] = str(options.refresh).lower()
        return await call(
            ApiRequest(
                method="GET", route=f"documents/{document_id}/stats/", query=query
            )
        )

    @server.tool(annotations=READ)
    async def list_document_page_ids(document_id: Identifier) -> JsonValue:
        """Return a raw list of all page IDs in native page order, possibly empty."""
        return await invoke("GET", f"documents/{document_id}/part_ids/")

    @server.tool(annotations=READ)
    async def find_pages_by_type(
        document_id: Identifier, query: ElementQuery
    ) -> JsonValue:
        """Get per-page counts for one region/line type or annotation taxonomy.

        type_id='none' selects untyped elements. Geometry results use
        document_part_id; annotation results use part_id. Preserve native keys.
        """
        return await call(
            ApiRequest(
                method="GET",
                route=f"documents/{document_id}/elements_by_type/",
                query={"category": query.category, "type": str(query.type_id)},
            )
        )
