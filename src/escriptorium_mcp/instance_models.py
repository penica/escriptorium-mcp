"""Inputs for image and text annotations on a document page."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.record_models import Patch

AnnotationKind = Literal["image", "text"]
Offset = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
Pixel = Annotated[int, Field(strict=True, ge=-2147483648, le=2147483647)]
AnnotationPoint = Annotated[list[Pixel], Field(min_length=2, max_length=2)]
Coordinates = Annotated[list[AnnotationPoint], Field(min_length=2)]


class AnnotationValue(Input):
    """A field value; null clears its content but does not remove its relation."""

    component: Identifier
    value: Annotated[str, Field(min_length=1)] | None


class AnnotationValues(Input):
    """Values are upserted by component ID, not replaced as a collection."""

    components: list[AnnotationValue] = Field(default_factory=list)
    comments: list[str] | None = Field(default_factory=list)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        """Reject duplicate components and nulls except nullable comments."""
        ids = [value.component for value in self.components]
        if len(ids) != len(set(ids)):
            msg = "Supply each component at most once."
            raise ValueError(msg)
        for name in self.model_fields_set - {"comments"}:
            if getattr(self, name) is None:
                msg = f"{name} cannot be null."
                raise ValueError(msg)
        return self


class ImageAnnotationCreate(AnnotationValues):
    """Rectangle corners or polygon vertices, in integer image pixels."""

    taxonomy: Identifier
    coordinates: Coordinates


class ImageAnnotationPatch(AnnotationValues, Patch):
    """Update supplied fields while preserving omitted values and components."""

    taxonomy: Identifier | None = None
    coordinates: Coordinates | None = None


class TextAnnotationCreate(AnnotationValues):
    """Text span identified by line IDs, a layer ID and zero-based offsets."""

    taxonomy: Identifier
    transcription: Identifier
    start_line: Identifier
    end_line: Identifier
    start_offset: Offset
    end_offset: Offset

    @model_validator(mode="after")
    def ordered_offsets(self) -> Self:
        """Require a same-line span to end at or after its start."""
        if self.start_line == self.end_line and self.end_offset < self.start_offset:
            msg = "A same-line span cannot end before its start."
            raise ValueError(msg)
        return self


class TextAnnotationPatch(AnnotationValues, Patch):
    """Change a span, its layer, taxonomy or values; omitted fields stay intact."""

    taxonomy: Identifier | None = None
    transcription: Identifier | None = None
    start_line: Identifier | None = None
    end_line: Identifier | None = None
    start_offset: Offset | None = None
    end_offset: Offset | None = None

    @model_validator(mode="after")
    def ordered_offsets(self) -> Self:
        """Validate a complete supplied same-line span."""
        if (
            self.start_line is not None
            and self.start_line == self.end_line
            and self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            msg = "A same-line span cannot end before its start."
            raise ValueError(msg)
        return self


class AnnotationTarget(Input):
    """Address an annotation within a document and page."""

    document_id: Identifier
    page_id: Identifier
    annotation_id: Identifier

    def route(self, kind: AnnotationKind) -> str:
        """Return the document-scoped annotation endpoint."""
        return (
            f"documents/{self.document_id}/parts/{self.page_id}/"
            f"annotations/{kind}/{self.annotation_id}/"
        )
