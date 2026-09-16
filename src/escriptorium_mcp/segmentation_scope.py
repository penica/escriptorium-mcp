"""Page ownership, geometry and optional-field checks before segmentation writes."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, JsonValue

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.ontology_native import Options
from escriptorium_mcp.segmentation_models import LineFields, LinePatch
from escriptorium_mcp.text_scope import RecordId, collection, require_page


class ElementState(RecordId):
    """Parse parent identity and geometry while retaining raw responses separately."""

    document_part: Identifier
    baseline: list[list[float]] | None = None
    mask: list[list[float]] | None = None


class DocumentTypes(RecordId):
    """Only document-enabled type identities are relevant to segmentation edits."""

    valid_line_types: list[RecordId] = Field(default_factory=list)
    valid_block_types: list[RecordId] = Field(default_factory=list)


def require_unique_ids(values: list[int]) -> None:
    """Native handlers may silently collapse duplicates, so reject them locally."""
    if len(set(values)) != len(values):
        msg = "Duplicate line IDs are not allowed."
        raise ToolError(msg)


def require_geometry(current: ElementState, changes: LinePatch) -> None:
    """Apply nullable geometry changes in memory before allowing the server write."""
    baseline = (
        changes.baseline if "baseline" in changes.model_fields_set else current.baseline
    )
    mask = changes.mask if "mask" in changes.model_fields_set else current.mask
    if not baseline and not mask:
        msg = "The resulting line must retain a baseline or mask."
        raise ToolError(msg)


@dataclass(frozen=True, slots=True)
class SegmentationScope:
    """Bind every segmentation action and reference check to one document page."""

    document_id: int
    page_id: int

    @property
    def route(self) -> str:
        """Return the authorized nested page route."""
        return f"documents/{self.document_id}/parts/{self.page_id}/"

    async def require_page(self) -> None:
        """Check the parent independently of legacy nested element endpoints."""
        _ = await require_page(self.document_id, self.page_id)

    async def detail(
        self, kind: Literal["lines", "blocks"], element_id: int
    ) -> JsonValue:
        """Read one scoped element and reject a mismatched upstream identity."""
        value = await invoke("GET", f"{self.route}{kind}/{element_id}/")
        record = ElementState.model_validate(value)
        if record.pk != element_id or record.document_part != self.page_id:
            msg = "The element is outside the requested page/document."
            raise ToolError(msg)
        return value

    async def selected(self, line_ids: list[int]) -> list[ElementState]:
        """Require the complete selection rather than permit a matched subset."""
        require_unique_ids(line_ids)
        records = [
            ElementState.model_validate(row)
            for row in await collection(self.route + "lines/")
        ]
        known = {row.pk: row for row in records if row.document_part == self.page_id}
        if not set(line_ids).issubset(known):
            msg = "A selected line is outside the requested page/document."
            raise ToolError(msg)
        return [known[line_id] for line_id in line_ids]

    async def line_references(self, lines: Sequence[LineFields]) -> None:
        """Validate supplied region links and enabled types before line writes."""
        regions = {line.region for line in lines if line.region is not None}
        if regions:
            known = {
                record.pk
                for row in await collection(self.route + "blocks/")
                if (record := ElementState.model_validate(row)).document_part
                == self.page_id
            }
            if not regions.issubset(known):
                msg = "A region is outside the requested page/document."
                raise ToolError(msg)
        await self.require_types(
            "lines", {line.typology for line in lines if line.typology is not None}
        )

    async def require_types(
        self, kind: Literal["lines", "blocks"], ids: set[int]
    ) -> None:
        """Accept only types currently enabled for this document."""
        if not ids:
            return
        document = DocumentTypes.model_validate(
            await invoke("GET", f"documents/{self.document_id}/")
        )
        types = {
            "lines": document.valid_line_types,
            "blocks": document.valid_block_types,
        }[kind]
        if document.pk != self.document_id or not ids.issubset(
            {row.pk for row in types}
        ):
            msg = "A typology is not enabled for the requested document."
            raise ToolError(msg)

    async def require_layers(self, ids: set[int]) -> None:
        """Nested new text must use document-owned transcription layers."""
        if not ids:
            return
        known = {
            RecordId.model_validate(row).pk
            for row in await collection(f"documents/{self.document_id}/transcriptions/")
        }
        if not ids.issubset(known):
            msg = "A transcription layer is outside the requested document."
            raise ToolError(msg)


async def require_lock_field(route: str) -> None:
    """Prevent older serializers silently dropping the requested locking field."""
    options = Options.model_validate(await invoke("OPTIONS", route))
    if not any(
        "locked" in fields and not fields["locked"].read_only
        for fields in options.actions.values()
    ):
        msg = "This server does not expose a writable locked region field."
        raise ToolError(msg)
