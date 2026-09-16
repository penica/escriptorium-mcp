"""Manual segmentation geometry and ordering tools."""

from typing import Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, Input, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.segmentation_models import (
    LineCreate,
    LinePatch,
    RegionCreate,
    RegionPatch,
)
from escriptorium_mcp.segmentation_scope import (
    ElementState,
    SegmentationScope,
    require_geometry,
    require_lock_field,
    require_unique_ids,
)


class ElementTarget(Input):
    """Address an existing line or region inside a page."""

    document_id: Identifier
    page_id: Identifier
    element_id: Identifier

    def route(self, kind: Literal["lines", "blocks"]) -> str:
        """Build the element address inside this page."""
        prefix = f"documents/{self.document_id}/parts/{self.page_id}/"
        return f"{prefix}{kind}/{self.element_id}/"


class PagePosition(Input):
    """Zero-based page position within the same document."""

    index: Annotated[int, Field(ge=0, strict=True)]


class LinePosition(Input):
    """A line's primary key and new reading-order index."""

    pk: Identifier
    order: Annotated[int, Field(ge=0, strict=True)]


class LineOrder(Input):
    """Explicit line order changes within one page."""

    lines: Annotated[list[LinePosition], Field(min_length=1)]


def register_segmentation(server: MCPServer) -> None:
    """Expose manual geometry editing separately from automatic segmentation."""

    @server.tool(annotations=CREATE)
    async def create_line(document_id: Identifier, line: LineCreate) -> JsonValue:
        """Create a line with a baseline or mask on line.document_part.

        Coordinates are image pixels. Optional region and typology references
        must belong to this page/document; external_id and order are editable.
        """
        scope = SegmentationScope(document_id, line.document_part)
        await scope.require_page()
        await scope.line_references([line])
        return await invoke("POST", scope.route + "lines/", line)

    @server.tool(annotations=CHANGE)
    async def update_line(target: ElementTarget, changes: LinePatch) -> JsonValue:
        """Edit line geometry, region, typology, external_id or reading-order index.

        Omit unchanged fields. Null clears nullable fields, but the final line
        must retain a baseline or mask. Supplied references are checked first.
        """
        scope = SegmentationScope(target.document_id, target.page_id)
        await scope.require_page()
        current = ElementState.model_validate(
            await scope.detail("lines", target.element_id)
        )
        require_geometry(current, changes)
        await scope.line_references([changes])
        return await invoke("PATCH", target.route("lines"), changes)

    @server.tool(annotations=CREATE)
    async def create_region(document_id: Identifier, region: RegionCreate) -> JsonValue:
        """Create a region polygon with optional typology, external_id and locked.

        Explicit locking requires writable server support. Locked is an editor
        cutting preference, not a permission lock; API edits remain possible.
        """
        scope = SegmentationScope(document_id, region.document_part)
        await scope.require_page()
        await scope.require_types(
            "blocks", {region.typology} if region.typology is not None else set()
        )
        route = scope.route + "blocks/"
        if "locked" in region.model_fields_set:
            await require_lock_field(route)
        return await invoke("POST", route, region)

    @server.tool(annotations=CHANGE)
    async def update_region(target: ElementTarget, changes: RegionPatch) -> JsonValue:
        """Edit a region polygon, typology, external_id or editor locking flag.

        Explicit locked changes probe writable server support before submitting.
        Locking does not prevent API edits or deletion. Omit unchanged fields;
        null clears typology/external_id but cannot remove the region polygon.
        """
        scope = SegmentationScope(target.document_id, target.page_id)
        await scope.require_page()
        _ = await scope.detail("blocks", target.element_id)
        await scope.require_types(
            "blocks", {changes.typology} if changes.typology is not None else set()
        )
        if "locked" in changes.model_fields_set:
            await require_lock_field(target.route("blocks"))
        return await invoke("PATCH", target.route("blocks"), changes)

    @server.tool(annotations=DELETE)
    async def delete_line(target: ElementTarget) -> JsonValue:
        """Delete a segmented line, attached text/history and cascaded relations."""
        scope = SegmentationScope(target.document_id, target.page_id)
        await scope.require_page()
        _ = await scope.detail("lines", target.element_id)
        return await invoke("DELETE", target.route("lines"))

    @server.tool(annotations=DELETE)
    async def delete_region(target: ElementTarget) -> JsonValue:
        """Delete a region; related line treatment follows server rules."""
        scope = SegmentationScope(target.document_id, target.page_id)
        await scope.require_page()
        _ = await scope.detail("blocks", target.element_id)
        return await invoke("DELETE", target.route("blocks"))

    @server.tool(annotations=CHANGE)
    async def move_page(
        document_id: Identifier,
        page_id: Identifier,
        position: PagePosition,
    ) -> JsonValue:
        """Reorder one page within its document using a zero-based index."""
        return await invoke(
            "POST", f"documents/{document_id}/parts/{page_id}/move/", position
        )

    @server.tool(annotations=CHANGE)
    async def reorder_lines(
        document_id: Identifier,
        page_id: Identifier,
        order: LineOrder,
    ) -> JsonValue:
        """Change explicit line reading-order indexes after checking page membership.

        Duplicate IDs are rejected; the native response lists whole-page orders.
        """
        line_ids = [line.pk for line in order.lines]
        require_unique_ids(line_ids)
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        _ = await scope.selected(line_ids)
        return await invoke("POST", scope.route + "lines/move/", order)
