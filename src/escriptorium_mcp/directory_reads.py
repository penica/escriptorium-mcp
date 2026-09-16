"""Complete visible directories with optional explicitly local string search."""

from typing import assert_never

from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp.account_models import DirectorySearch
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import call
from escriptorium_mcp.pagination import (
    PageSelection,
    annotate_filtered_page,
    paginated_request,
)
from escriptorium_mcp.text_scope import RecordPage


def _searchable(value: JsonValue) -> str | None:
    """Compare string fields only, tolerating omitted/null or differently typed data."""
    match value:
        case str():
            return value
        case None | bool() | int() | float() | list() | dict():
            return None
        case _:
            assert_never(value)


def _directory_rows(raw: JsonValue) -> list[JsonValue]:
    """Parse bare or paginated results only when local filtering is requested."""
    parsed = TypeAdapter[list[JsonValue] | RecordPage](
        list[JsonValue] | RecordPage
    ).validate_python(raw)
    match parsed:
        case RecordPage(results=rows):
            return rows
        case list():
            return parsed
        case _:
            assert_never(parsed)


async def read_directory(
    route: str,
    search: DirectorySearch | None,
    fields: tuple[str, ...],
    *,
    pagination: PageSelection | None = None,
) -> JsonValue:
    """Fetch the entire authorized collection before any local casefold comparison."""
    raw = await call(
        paginated_request(route, pagination, page_size_supported=True)
        if pagination is not None
        else ApiRequest(
            method="GET", route=route, paginate=True, strict_pagination=True
        )
    )
    if search is None:
        return raw
    records = _directory_rows(raw)
    needle = search.casefold()
    matches: list[JsonValue] = []
    parser = TypeAdapter[dict[str, JsonValue]](dict[str, JsonValue])
    for row in records:
        record = parser.validate_python(row)
        values = [_searchable(record.get(field)) for field in fields]
        if any(needle in value.casefold() for value in values if value is not None):
            matches.append(row)
    if pagination is not None:
        return annotate_filtered_page(raw, matches)
    return {"count": len(matches), "next": None, "previous": None, "results": matches}
