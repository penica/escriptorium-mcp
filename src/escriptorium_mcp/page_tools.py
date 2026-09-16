"""Native page lookup, filtering, movement and image actions."""

from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, FilePath, JsonValue

from escriptorium_mcp.api import JOB, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, Request, call
from escriptorium_mcp.page_models import (
    Angle,
    BulkPageMove,
    CropBox,
    ImageMetadata,
    PageByOrder,
    PageFilters,
    PageMovePayload,
    Pixel,
    Rotation,
)
from escriptorium_mcp.page_scope import require_crop, require_move
from escriptorium_mcp.pagination import PageSelection, paginated_request
from escriptorium_mcp.text_scope import require_page


async def list_filtered_pages(
    document_id: Identifier,
    filters: PageFilters,
    pagination: PageSelection | None = None,
) -> JsonValue:
    """Preserve native fields and pagination with a documented query whitelist."""
    query: dict[str, str] = {}
    if filters.name is not None:
        query["name"] = filters.name
    if filters.ordering is not None:
        query["ordering"] = ",".join(filters.ordering)
    return await call(
        paginated_request(
            f"documents/{document_id}/parts/",
            pagination,
            query=query,
            page_size_supported=False,
        )
    )


async def list_page_records(
    document_id: Identifier,
    filters: PageFilters | None,
    pagination: PageSelection | None,
) -> JsonValue:
    """Retain legacy page reads unless one native page is requested."""
    if filters is not None:
        return await list_filtered_pages(document_id, filters, pagination)
    request = (
        Request(operation="list_pages", document_id=document_id)
        if pagination is None
        else paginated_request(
            f"documents/{document_id}/parts/",
            pagination,
            page_size_supported=False,
        )
    )
    return await call(request)


async def list_page_elements(
    operation: Literal["list_lines", "list_regions"],
    route: str,
    document_id: Identifier,
    page_id: Identifier,
    pagination: PageSelection | None,
) -> JsonValue:
    """Retain legacy geometry reads unless one native page is requested."""
    request = (
        Request(operation=operation, document_id=document_id, page_id=page_id)
        if pagination is None
        else paginated_request(route, pagination, page_size_supported=True)
    )
    return await call(request)


async def read_page_transcriptions(
    document_id: Identifier,
    page_id: Identifier,
    transcription_id: Identifier | None,
    pagination: PageSelection | None,
) -> JsonValue:
    """Retain legacy text reads unless one native page is requested."""
    route = f"documents/{document_id}/parts/{page_id}/transcriptions/"
    request = paginated_request(
        route,
        pagination,
        query=(
            {"transcription": str(transcription_id)}
            if transcription_id is not None
            else None
        ),
        page_size_supported=False,
    )
    if transcription_id is not None:
        _ = await invoke(
            "GET", f"documents/{document_id}/transcriptions/{transcription_id}/"
        )
        return await call(request)
    legacy = Request(
        operation="get_page_transcriptions",
        document_id=document_id,
        page_id=page_id,
    )
    return await call(legacy if pagination is None else request)


async def transform_image(route: str, payload: BaseModel) -> JsonValue:
    """Send exactly one transform and retain partial-effect context on failures."""
    try:
        return await call(
            ApiRequest(method="POST", route=route, body_json=payload.model_dump_json()),
            timeout_seconds=1800,
        )
    except ToolError as error:
        msg = (
            f"{error} Image or geometry changes may have partially completed. "
            "Inspect the page before retrying; this operation is not atomic."
        )
        raise ToolError(msg) from None


def register_page_operations(server: MCPServer) -> None:
    """Register five native operations with explicit destructive image semantics."""

    @server.tool(annotations=READ)
    async def get_page_by_order(document_id: Identifier, order: Pixel) -> JsonValue:
        """Read a page by zero-based order, distinct from its page ID.

        Follows only one same-origin redirect to this document's page detail.
        Missing/out-of-bounds order and unexpected redirect targets are errors.
        """
        return await call(PageByOrder(document_id=document_id, order=order))

    @server.tool(annotations=JOB)
    async def rotate_page(
        document_id: Identifier, page_id: Identifier, angle: Angle
    ) -> JsonValue:
        """Rotate clockwise by a nonzero integer from -359 through 359 degrees.

        Expands the canvas and transforms lines, regions and image annotations;
        transcription character graphs stay unchanged. Returns synchronous done,
        not a job ID; remaining thumbnails may still be queued. Files/rows can
        change partially on failure: inspect before retrying. Never auto-retries.
        """
        payload = Rotation(angle=angle)
        route = await require_page(document_id, page_id)
        return await transform_image(route + "rotate/", payload)

    @server.tool(annotations=JOB)
    async def crop_page(
        document_id: Identifier, page_id: Identifier, box: CropBox
    ) -> JsonValue:
        """Destructively crop within current image bounds using integer corners.

        Overwrites the image and translates line/region geometry without clipping
        outside coordinates. Image annotations and character graphs are unchanged.
        Does not refresh thumbnails, file size or reading order. Returns native
        done, without a job ID. Failures can leave partial changes; inspect before
        retrying. No automatic retry or recovery of discarded pixels is provided.
        """
        route = f"documents/{document_id}/parts/{page_id}/"
        await require_crop(route, page_id, box)
        return await transform_image(route + "crop/", box)

    @server.tool(annotations=JOB)
    async def bulk_move_pages(document_id: Identifier, move: BulkPageMove) -> JsonValue:
        """Move a complete page selection at an original-order insertion index.

        Index -1 appends; otherwise use 0 through the current page count. Selected
        pages retain their current relative order, irrespective of supplied ID
        order. Preflight checks every ID but does not lock concurrent edits.
        Returns the native moved status; no updated list or job ID is invented.
        """
        await require_move(document_id, move)
        return await invoke(
            "POST",
            f"documents/{document_id}/bulk_move_parts/",
            PageMovePayload(parts=move.page_ids, index=move.index),
        )

    @server.tool(annotations=JOB)
    async def replace_page_image(
        document_id: Identifier, page_id: Identifier, image_path: FilePath
    ) -> JsonValue:
        """Replace a page image from an existing file on the MCP server machine.

        Sends multipart image plus its measured byte count. Existing geometry and
        text are not resized or reprojected. PATCH does not run upload conversion,
        thumbnail or duplicate-filename hooks. Arbitrary image_file_size edits are
        not exposed; original_filename can be changed separately with update_page.
        """
        route = await require_page(document_id, page_id)
        metadata = ImageMetadata(image_file_size=image_path.stat().st_size)
        return await call(
            ApiRequest(
                method="PATCH",
                route=route,
                file_path=image_path,
                body_json=metadata.model_dump_json(),
            ),
            timeout_seconds=1800,
        )
