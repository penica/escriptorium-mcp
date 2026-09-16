"""Manual segmentation geometry and ordering tools."""

from typing import Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, Input, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.record_models import Patch

Coordinate = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Point = Annotated[list[Coordinate], Field(min_length=2, max_length=2)]
Polygon = Annotated[list[Point], Field(min_length=3)]
Baseline = Annotated[list[Point], Field(min_length=2)]


class LineCreate(Input):
    """Baseline coordinates in image pixels and optional region/polygon."""

    document_part: Identifier
    baseline: Baseline
    mask: Polygon | None = None
    region: Identifier | None = None
    typology: Identifier | None = None


class LinePatch(Patch):
    """Change supplied geometry fields; null clears a polygon or region."""

    baseline: Baseline | None = None
    mask: Polygon | None = None
    region: Identifier | None = None
    typology: Identifier | None = None


class RegionCreate(Input):
    """A page region polygon in image pixels."""

    document_part: Identifier
    box: Polygon
    typology: Identifier | None = None


class RegionPatch(Patch):
    """Edit a region's outline or classification."""

    box: Polygon | None = None
    typology: Identifier | None = None


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
        """Create a segmented line on line.document_part; coordinates are pixels."""
        return await invoke(
            "POST", f"documents/{document_id}/parts/{line.document_part}/lines/", line
        )

    @server.tool(annotations=CHANGE)
    async def update_line(target: ElementTarget, changes: LinePatch) -> JsonValue:
        """Edit an existing line's baseline, mask, region or type."""
        return await invoke(
            "PATCH",
            target.route("lines"),
            changes,
        )

    @server.tool(annotations=CREATE)
    async def create_region(document_id: Identifier, region: RegionCreate) -> JsonValue:
        """Create a region polygon on region.document_part."""
        return await invoke(
            "POST",
            f"documents/{document_id}/parts/{region.document_part}/blocks/",
            region,
        )

    @server.tool(annotations=CHANGE)
    async def update_region(target: ElementTarget, changes: RegionPatch) -> JsonValue:
        """Edit an existing region's polygon or type."""
        return await invoke(
            "PATCH",
            target.route("blocks"),
            changes,
        )

    @server.tool(annotations=DELETE)
    async def delete_line(target: ElementTarget) -> JsonValue:
        """Delete a segmented line and its attached transcription text."""
        return await invoke(
            "DELETE",
            target.route("lines"),
        )

    @server.tool(annotations=DELETE)
    async def delete_region(target: ElementTarget) -> JsonValue:
        """Delete a region; related line treatment follows server rules."""
        return await invoke(
            "DELETE",
            target.route("blocks"),
        )

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
        """Change line reading order within a page."""
        return await invoke(
            "POST", f"documents/{document_id}/parts/{page_id}/lines/move/", order
        )
