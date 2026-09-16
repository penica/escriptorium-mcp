"""Native segmentation bulk actions, detailed reads and geometry maintenance."""

from typing import Annotated, Final

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, JOB, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.segmentation import ElementTarget
from escriptorium_mcp.segmentation_models import (
    BulkCreateWire,
    BulkLineCreate,
    BulkLineCreateWire,
    BulkLinePatch,
    BulkUpdateWire,
    LineIds,
    MergeIds,
    SelectedLines,
)
from escriptorium_mcp.segmentation_scope import (
    SegmentationScope,
    require_geometry,
    require_unique_ids,
)

MIN_MERGE_BASELINE_POINTS: Final = 2

CreateLines = Annotated[list[BulkLineCreate], Field(min_length=1)]
UpdateLines = Annotated[list[BulkLinePatch], Field(min_length=1)]


def register_segmentation_reads(server: MCPServer) -> None:
    """Register individual geometry reads with parent-page verification."""

    @server.tool(annotations=READ)
    async def get_line(target: ElementTarget) -> JsonValue:
        """Read one segmented line including its detailed transcription records."""
        scope = SegmentationScope(target.document_id, target.page_id)
        await scope.require_page()
        return await scope.detail("lines", target.element_id)

    @server.tool(annotations=READ)
    async def get_region(target: ElementTarget) -> JsonValue:
        """Read one region, including locking when supported by the server."""
        scope = SegmentationScope(target.document_id, target.page_id)
        await scope.require_page()
        return await scope.detail("blocks", target.element_id)


def register_segmentation_expansion(server: MCPServer) -> None:
    """Expose native routes without inventing completion or lossless restoration."""
    register_segmentation_reads(server)

    @server.tool(annotations=CREATE)
    async def bulk_create_lines(
        document_id: Identifier, page_id: Identifier, lines: CreateLines
    ) -> JsonValue:
        """Create segmented lines and optional nested text in document-owned layers.

        Coordinates are image pixels. A baseline or mask is required. Native
        creation is atomic on the audited server; preflight is not a lock.
        """
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        await scope.line_references(lines)
        await scope.require_layers(
            {text.transcription for line in lines for text in line.transcriptions}
        )
        payload = BulkCreateWire(
            lines=[
                BulkLineCreateWire.model_validate(
                    {**line.model_dump(exclude_unset=True), "document_part": page_id}
                )
                for line in lines
            ]
        )
        return await invoke("POST", scope.route + "lines/bulk_create/", payload)

    @server.tool(annotations=JOB)
    async def bulk_update_lines(
        document_id: Identifier, page_id: Identifier, lines: UpdateLines
    ) -> JsonValue:
        """Edit existing segmented lines with one native PUT after scoped preflight.

        A later save failure can leave earlier edits applied. Never retry blindly;
        re-read affected records. Omitted fields remain, explicit null clears
        nullable fields. Every final line needs a baseline or mask.
        """
        require_unique_ids([line.pk for line in lines])
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        current = await scope.selected([line.pk for line in lines])
        for record, changes in zip(current, lines, strict=True):
            require_geometry(record, changes)
        await scope.line_references(lines)
        try:
            return await invoke(
                "PUT", scope.route + "lines/bulk_update/", BulkUpdateWire(lines=lines)
            )
        except ToolError as error:
            msg = (
                "Bulk update may have partially applied changes. "
                f"Re-read the affected lines before retrying. {error}"
            )
            raise ToolError(msg) from None

    @server.tool(annotations=DELETE)
    async def bulk_delete_lines(
        document_id: Identifier, page_id: Identifier, line_ids: LineIds
    ) -> JsonValue:
        """Delete selected geometry, attached text/history and cascaded relations.

        Every selected ID must belong to this page. Returned deleted records are
        not a complete backup of all cascaded objects. Preflight is not a lock.
        """
        require_unique_ids(line_ids)
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        _ = await scope.selected(line_ids)
        return await invoke(
            "POST", scope.route + "lines/bulk_delete/", SelectedLines(lines=line_ids)
        )

    @server.tool(annotations=JOB)
    async def merge_lines(
        document_id: Identifier, page_id: Identifier, line_ids: MergeIds
    ) -> JsonValue:
        """Replace 2-8 distinct baseline-bearing lines with one merged line.

        Original lines are deleted. The server chooses geometric/text order,
        region and type; character graphs, confidence and history are not
        preserved. The mask may need explicit regeneration afterward.
        """
        require_unique_ids(line_ids)
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        records = await scope.selected(line_ids)
        if any(
            not record.baseline or len(record.baseline) < MIN_MERGE_BASELINE_POINTS
            for record in records
        ):
            msg = "Every merged line must have a baseline with at least two points."
            raise ToolError(msg)
        return await invoke(
            "POST", scope.route + "lines/merge/", SelectedLines(lines=line_ids)
        )

    @server.tool(annotations=JOB)
    async def regenerate_line_masks(
        document_id: Identifier, page_id: Identifier, line_ids: LineIds | None = None
    ) -> JsonValue:
        """Queue mask regeneration for selected lines or all eligible page lines.

        A status ok response means submitted, not completed. The native response
        has no task ID. Omit line_ids for all lines; an empty list is invalid.
        """
        if line_ids is not None:
            require_unique_ids(line_ids)
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        if line_ids is not None:
            _ = await scope.selected(line_ids)
        return await call(
            ApiRequest(
                method="POST",
                route=scope.route + "reset_masks/",
                body_json="null",
                query={"only": ",".join(map(str, line_ids))}
                if line_ids is not None
                else {},
            )
        )

    @server.tool(annotations=CHANGE)
    async def recalculate_line_order(
        document_id: Identifier, page_id: Identifier
    ) -> JsonValue:
        """Replace manual line ordering using page geometry and document direction.

        This native action runs synchronously and returns whole-page line orders.
        """
        scope = SegmentationScope(document_id, page_id)
        await scope.require_page()
        return await call(
            ApiRequest(
                method="POST",
                route=scope.route + "recalculate_ordering/",
                body_json="null",
            )
        )
