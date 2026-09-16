"""Preflight ownership of bulk text records on legacy and current APIs."""

from typing import ClassVar

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.record_models import LineText
from escriptorium_mcp.text_models import BulkTextPatch


class RecordId(BaseModel):
    """Parse IDs while allowing additional upstream metadata."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    pk: Identifier


class TextRecord(RecordId):
    """Preserve identity and current line/layer links for mutation preflight."""

    line: Identifier
    transcription: Identifier


class RecordPage(BaseModel):
    """Collection envelope after the worker has followed every pagination link."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    results: list[JsonValue]


async def collection(route: str) -> list[JsonValue]:
    """Accept both bare collections and fully paginated DRF responses."""
    value = TypeAdapter[list[JsonValue] | RecordPage](
        list[JsonValue] | RecordPage
    ).validate_python(await call(ApiRequest(method="GET", route=route, paginate=True)))
    return value.results if isinstance(value, RecordPage) else value


def require_unique(values: list[int] | list[tuple[int, int]]) -> None:
    """Reject duplicate record IDs or conflicting line/layer pairs before writes."""
    if len(set(values)) != len(values):
        msg = "Duplicate transcription IDs or line/layer pairs are not allowed."
        raise ToolError(msg)


async def require_page(document_id: Identifier, page_id: Identifier) -> str:
    """Confirm the parent page before trusting legacy nested collection routes."""
    route = f"documents/{document_id}/parts/{page_id}/"
    page = RecordId.model_validate(await invoke("GET", route))
    if page.pk != page_id:
        msg = "The server returned a different page; no writes were sent."
        raise ToolError(msg)
    return route


async def require_references(
    document_id: Identifier,
    page_route: str,
    pairs: list[tuple[int, int]],
) -> None:
    """Verify every supplied line belongs to the page and layer to the document."""
    lines = {
        RecordId.model_validate(row).pk
        for row in await collection(page_route + "lines/")
    }
    layers = {
        RecordId.model_validate(row).pk
        for row in await collection(f"documents/{document_id}/transcriptions/")
    }
    if any(line not in lines or layer not in layers for line, layer in pairs):
        msg = "A line or transcription layer is outside the requested page/document."
        raise ToolError(msg)


async def existing_records(page_route: str) -> list[TextRecord]:
    """Read all scoped record identities, including rows beyond the first page."""
    return [
        TextRecord.model_validate(row)
        for row in await collection(page_route + "transcriptions/")
    ]


async def preflight_create(
    document_id: Identifier, page_id: Identifier, lines: list[LineText]
) -> str:
    """Check scope and duplicate pairs without claiming a transaction or lock."""
    pairs = [(line.line, line.transcription) for line in lines]
    require_unique(pairs)
    route = await require_page(document_id, page_id)
    await require_references(document_id, route, pairs)
    return route + "transcriptions/"


async def preflight_update(
    document_id: Identifier, page_id: Identifier, lines: list[BulkTextPatch]
) -> str:
    """Resolve record membership and resulting references before one native PUT."""
    require_unique([line.pk for line in lines])
    route = await require_page(document_id, page_id)
    records = await existing_records(route)
    current = {row.pk: row for row in records}
    if any(line.pk not in current for line in lines):
        msg = "A transcription record is outside the requested page/document."
        raise ToolError(msg)
    pairs = [
        (
            line.line if line.line is not None else current[line.pk].line,
            line.transcription
            if line.transcription is not None
            else current[line.pk].transcription,
        )
        for line in lines
    ]
    require_unique(pairs)
    changed = {line.pk for line in lines}
    occupied = {
        (row.line, row.transcription) for row in records if row.pk not in changed
    }
    if occupied.intersection(pairs):
        msg = "An unchanged record already uses a requested line/layer pair."
        raise ToolError(msg)
    await require_references(document_id, route, pairs)
    return route + "transcriptions/"


async def preflight_clear(
    document_id: Identifier, page_id: Identifier, record_ids: list[int]
) -> str:
    """Prevent old bulk-delete handlers from clearing globally selected IDs."""
    require_unique(record_ids)
    route = await require_page(document_id, page_id)
    known = {record.pk for record in await existing_records(route)}
    if not set(record_ids).issubset(known):
        msg = "A transcription record is outside the requested page/document."
        raise ToolError(msg)
    return route + "transcriptions/"
