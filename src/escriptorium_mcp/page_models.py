"""Validated page selections, image coordinates and native action payloads."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

Pixel = Annotated[int, Field(strict=True, ge=0)]
Angle = Annotated[int, Field(strict=True, ge=-359, le=359)]
PageOrdering = Literal[
    "order",
    "-order",
    "name",
    "-name",
    "original_filename",
    "-original_filename",
    "updated_at",
    "-updated_at",
]


class PageFilters(Input):
    """Native name/filename substring search and ordered sort fields."""

    name: str | None = None
    ordering: Annotated[list[PageOrdering], Field(min_length=1)] | None = None


class PageByOrder(Input):
    """Private request for a constrained single-redirect page lookup."""

    operation: Literal["page_by_order"] = "page_by_order"
    document_id: Identifier
    order: Pixel


class Rotation(Input):
    """Clockwise integer degrees, excluding the server's invalid zero angle."""

    angle: Angle

    @model_validator(mode="after")
    def require_rotation(self) -> Self:
        """Reject zero before any page lookup or image write."""
        if self.angle == 0:
            msg = "Rotation angle must be nonzero."
            raise ValueError(msg)
        return self


class CropBox(Input):
    """Integer corners in the current image, with a strictly positive area."""

    x1: Pixel
    y1: Pixel
    x2: Pixel
    y2: Pixel

    @model_validator(mode="after")
    def require_area(self) -> Self:
        """Reject reversed or empty rectangles before server mutation."""
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            msg = "Crop corners must define a positive width and height."
            raise ValueError(msg)
        return self


class BulkPageMove(Input):
    """A complete distinct selection and insertion position; -1 appends."""

    page_ids: Annotated[list[Identifier], Field(min_length=1)]
    index: Annotated[int, Field(strict=True, ge=-1)]

    @model_validator(mode="after")
    def require_distinct(self) -> Self:
        """Prevent the server silently collapsing repeated page identities."""
        if len(self.page_ids) != len(set(self.page_ids)):
            msg = "Duplicate page IDs are not allowed."
            raise ValueError(msg)
        return self


class PageMovePayload(Input):
    """Native bulk-move field names after document membership preflight."""

    parts: list[Identifier]
    index: int


class ImageMetadata(Input):
    """Replacement file size is measured locally, never supplied by the caller."""

    image_file_size: Annotated[int, Field(ge=0)]
