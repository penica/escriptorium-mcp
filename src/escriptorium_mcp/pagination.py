"""Shared opt-in native-page selection and response metadata."""

from collections.abc import Mapping, Sequence
from typing import Annotated, ClassVar, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ConfigDict, Field, JsonValue, TypeAdapter

from escriptorium_mcp.api import ApiRequest, Input

PositivePage = Annotated[int, Field(gt=0, strict=True)]
NativePageSize = Annotated[int, Field(gt=0, le=50, strict=True)]


class PageSelection(Input):
    """Select one native result page; native page sizes are capped at 50."""

    page: PositivePage = 1
    page_size: NativePageSize | None = None


class PaginationMetadata(Input):
    """Disclose the scope and continuation state of one native page."""

    mode: Literal["native_page"]
    page: PositivePage
    page_size: NativePageSize | None
    returned_count: Annotated[int, Field(ge=0, strict=True)]
    native_total: Annotated[int, Field(ge=0, strict=True)] | None
    native_total_scope: Literal["collection", "unknown"]
    filtered_total: Annotated[int, Field(ge=0, strict=True)] | None
    filtered_total_scope: Literal["not_filtered", "source_page"]
    has_next: bool
    has_previous: bool
    next_page: PositivePage | None
    previous_page: PositivePage | None
    collection_consistency: Literal["snapshot_not_guaranteed"]


class NativePage(Input):
    """Parse the worker's guarded one-page envelope while retaining native fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    count: JsonValue = None
    results: list[JsonValue]
    pagination: PaginationMetadata


def paginated_request(
    route: str,
    pagination: PageSelection | None,
    *,
    query: Mapping[str, str] | None = None,
    page_size_supported: bool,
) -> ApiRequest:
    """Build an all-results legacy request or exactly one guarded native page."""
    native_query = dict(query or {})
    if pagination is None:
        return ApiRequest(method="GET", route=route, query=native_query, paginate=True)
    if pagination.page_size is not None and not page_size_supported:
        msg = f"{route} does not support page_size."
        raise ToolError(msg)
    if "page" in native_query or "paginate_by" in native_query:
        msg = "Pagination query keys are reserved for PageSelection."
        raise ValueError(msg)
    native_query["page"] = str(pagination.page)
    if pagination.page_size is not None:
        native_query["paginate_by"] = str(pagination.page_size)
    return ApiRequest(
        method="GET",
        route=route,
        query=native_query,
        native_page=True,
        strict_pagination=True,
        single_attempt=True,
    )


def annotate_filtered_page(
    raw: JsonValue, filtered_results: Sequence[JsonValue]
) -> JsonValue:
    """Replace page rows without claiming a full-collection filtered total."""
    page = NativePage.model_validate(raw)
    results = list(filtered_results)
    metadata = page.pagination.model_copy(
        update={
            "returned_count": len(results),
            "filtered_total": len(results),
            "filtered_total_scope": "source_page",
        }
    )
    output = page.model_dump()
    output["count"] = None
    output["results"] = results
    output["pagination"] = metadata.model_dump()
    return TypeAdapter[JsonValue](JsonValue).validate_python(output)
