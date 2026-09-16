"""Validated segmentation geometry and native bulk-action inputs."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.text_models import CharacterGraph, Content, Score

Coordinate = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Point = Annotated[list[Coordinate], Field(min_length=2, max_length=2)]
Polygon = Annotated[list[Point], Field(min_length=3)]
Baseline = Annotated[list[Point], Field(min_length=2)]
ExternalId = Annotated[str, Field(max_length=128)]
Order = Annotated[int, Field(ge=0, strict=True)]
LineIds = Annotated[list[Identifier], Field(min_length=1)]
MergeIds = Annotated[list[Identifier], Field(min_length=2, max_length=8)]


class LineFields(Input):
    """Writable line fields, excluding identity and parent-page changes."""

    baseline: Baseline | None = None
    mask: Polygon | None = None
    region: Identifier | None = None
    typology: Identifier | None = None
    external_id: ExternalId | None = None
    order: Order | None = None

    @model_validator(mode="after")
    def require_nonnull_order(self) -> Self:
        """Preserve the server default when order is omitted; reject explicit null."""
        if "order" in self.model_fields_set and self.order is None:
            msg = "order cannot be null."
            raise ValueError(msg)
        return self


class LineGeometry(LineFields):
    """New lines need a baseline, a mask, or both."""

    @model_validator(mode="after")
    def require_geometry(self) -> Self:
        """Reject new lines without usable geometry before network access."""
        if self.baseline is None and self.mask is None:
            msg = "A line requires a baseline or mask."
            raise ValueError(msg)
        return self


class LineCreate(LineGeometry):
    """Single-line creation explicitly names its parent page."""

    document_part: Identifier


class LinePatch(LineFields):
    """Omitted fields survive; nullable geometry requires final-state preflight."""

    @model_validator(mode="after")
    def require_change(self) -> Self:
        """Require an edit beyond the bulk identity."""
        if not self.model_fields_set - {"pk"}:
            msg = "Supply at least one line field to update."
            raise ValueError(msg)
        return self


class NestedTranscription(Input):
    """The bulk endpoint assigns the new line ID; only its layer is supplied."""

    transcription: Identifier
    content: Content = ""
    graphs: list[CharacterGraph] | None = None
    avg_confidence: Score | None = None


class BulkLineCreate(LineGeometry):
    """New line geometry with optional text in document-owned layers."""

    transcriptions: list[NestedTranscription] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_distinct_layers(self) -> Self:
        """Require one text record per layer for each newly created line."""
        layers = [record.transcription for record in self.transcriptions]
        if len(set(layers)) != len(layers):
            msg = "Duplicate transcription layers on one line are not allowed."
            raise ValueError(msg)
        return self


class BulkLinePatch(LinePatch):
    """An existing line identity and supplied changes within the URL page."""

    pk: Identifier


class RegionFields(Input):
    """Editable region fields; locked controls editor cutting, not permissions."""

    typology: Identifier | None = None
    external_id: ExternalId | None = None
    locked: bool | None = None

    @model_validator(mode="after")
    def require_nonnull_lock(self) -> Self:
        """Explicit lock changes must be booleans."""
        if "locked" in self.model_fields_set and self.locked is None:
            msg = "locked cannot be null."
            raise ValueError(msg)
        return self


class RegionCreate(RegionFields):
    """A page region polygon in image pixels."""

    document_part: Identifier
    box: Polygon


class RegionPatch(RegionFields):
    """Edit supplied region fields without clearing its required outline."""

    box: Polygon | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        """Require a meaningful edit and reject null region geometry."""
        if not self.model_fields_set:
            msg = "Supply at least one region field to update."
            raise ValueError(msg)
        if "box" in self.model_fields_set and self.box is None:
            msg = "box cannot be null."
            raise ValueError(msg)
        return self


class BulkLineCreateWire(BulkLineCreate):
    """Parent binding is generated internally, never accepted from bulk callers."""

    document_part: Identifier


class BulkCreateWire(Input):
    """Private wrapper includes the correct page for older API implementations."""

    lines: list[BulkLineCreateWire]


class BulkUpdateWire(Input):
    """Native bulk-update wrapper."""

    lines: list[BulkLinePatch]


class SelectedLines(Input):
    """Native destructive actions expect line IDs under the lines key."""

    lines: list[Identifier]
