"""Document membership and current image bounds before page mutations."""

from typing import Annotated, ClassVar

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.page_models import BulkPageMove, CropBox
from escriptorium_mcp.text_scope import RecordId, collection


class PageDocument(RecordId):
    """Read only the document's enabled part types for metadata edits."""

    valid_part_types: list[RecordId] = Field(default_factory=list)


class CurrentImage(BaseModel):
    """Parse actual image dimensions without requiring unrelated image fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    size: tuple[
        Annotated[int, Field(strict=True, gt=0)],
        Annotated[int, Field(strict=True, gt=0)],
    ]


class CropPage(RecordId):
    """The identity and dimensions needed for a bounded crop."""

    image: CurrentImage


async def require_part_type(document_id: Identifier, typology: Identifier) -> None:
    """Permit only a page type enabled for the requested document."""
    document = PageDocument.model_validate(
        await invoke("GET", f"documents/{document_id}/")
    )
    if document.pk != document_id or typology not in {
        row.pk for row in document.valid_part_types
    }:
        msg = "The typology is not enabled for the requested document."
        raise ToolError(msg)


async def require_crop(page_route: str, page_id: Identifier, box: CropBox) -> None:
    """Check current dimensions and scoped identity without changing geometry."""
    page = CropPage.model_validate(await invoke("GET", page_route))
    if page.pk != page_id:
        msg = "The server returned a different page; no writes were sent."
        raise ToolError(msg)
    width, height = page.image.size
    if box.x2 > width or box.y2 > height:
        msg = "Crop corners exceed the current image bounds."
        raise ToolError(msg)


async def require_move(document_id: Identifier, move: BulkPageMove) -> None:
    """Authorize the document and require every selected page before one move."""
    document = RecordId.model_validate(await invoke("GET", f"documents/{document_id}/"))
    if document.pk != document_id:
        msg = "The server returned a different document; no writes were sent."
        raise ToolError(msg)
    known = {
        RecordId.model_validate(row).pk
        for row in await collection(f"documents/{document_id}/parts/")
    }
    if not set(move.page_ids).issubset(known):
        msg = "A selected page is outside the requested document."
        raise ToolError(msg)
    if move.index > len(known):
        msg = "The insertion index exceeds the document's page count."
        raise ToolError(msg)
