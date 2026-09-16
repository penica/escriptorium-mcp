"""Native project/document reads and expanded project settings operations."""

from typing import Literal

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.font_scope import save_record
from escriptorium_mcp.pagination import PageSelection, paginated_request
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
    query: dict[str, str],
    pagination: PageSelection | None = None,
) -> ApiRequest:
    """Serialize only native supported filters while retaining full pagination."""
    return paginated_request(route, pagination, query=query, page_size_supported=True)


async def list_project_records(
    filters: ProjectFilters | None = None,
    pagination: PageSelection | None = None,
) -> JsonValue:
    """Keep raw fields for both no-argument and filtered project lists."""
    options = filters or ProjectFilters()
    query = {
        key: value
        for key, value in (
            ("name", options.name),
            ("tags", options.tags),
            (
                "ordering",
                ",".join(options.ordering) if options.ordering is not None else None,
            ),
        )
        if value is not None
    }
    return await call(_listing("projects/", query, pagination))


async def list_document_records(
    filters: DocumentFilters | None = None,
    pagination: PageSelection | None = None,
) -> JsonValue:
    """Keep native document fields, counts and duplicate OR-filter matches."""
    options = filters or DocumentFilters()
    query = {
        key: value
        for key, value in (
            ("name", options.name),
            ("tags", options.tags),
            (
                "ordering",
                ",".join(options.ordering) if options.ordering is not None else None,
            ),
            ("project", str(options.project) if options.project is not None else None),
        )
        if value is not None
    }
    return await call(_listing("documents/", query, pagination))


async def create_project_record(
    name: RecordName, settings: ProjectCreateSettings | None = None
) -> JsonValue:
    """Preserve the name-only create call while allowing native optional settings."""
    body: dict[str, JsonValue] = {"name": name}
    if settings is not None:
        if "guidelines" in settings.model_fields_set:
            body["guidelines"] = settings.guidelines
        if "transcription_font" in settings.model_fields_set:
            body["transcription_font"] = settings.transcription_font
        if settings.tags is not None:
            await require_personal_tags(settings.tags)
            body["tags"] = list(settings.tags)
    data = ProjectCreate.model_validate(body)
    return await save_record("POST", "projects/", data, data.transcription_font)


def register_record_expansion(server: MCPServer) -> None:
    """Register project settings and document aggregate/page-ID native reads."""

    @server.tool(annotations=CHANGE)
    async def update_project(
        project_id: Identifier, changes: ProjectPatch
    ) -> JsonValue:
        """Update project name, guidelines or complete personal-tag assignments.

        Tags replace all assignments; [] clears them. Guidelines accept null or
        blank to clear. transcription_font changes presentation for inheriting
        documents; null restores user/default fallback without changing document
        overrides. Preflight reads do not lock records against other edits.
        """
        if changes.tags is not None:
            _ = await require_project(project_id)
            await require_personal_tags(changes.tags)
        return await save_record(
            "PATCH", f"projects/{project_id}/", changes, changes.transcription_font
        )

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
