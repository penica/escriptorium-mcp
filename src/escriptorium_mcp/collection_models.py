"""Explicit collection membership replacement and default layer selections."""

from typing import Annotated, Self

from pydantic import AfterValidator, Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.project_models import RecordName

DocumentKey = Annotated[str, Field(strict=True, pattern=r"^[1-9][0-9]*$")]
DefaultTranscriptions = dict[DocumentKey, Identifier]


class CollectionMember(Input):
    """A page/layer pair with document context used only for scope preflight."""

    document_id: Identifier
    page_id: Identifier
    transcription_id: Identifier


def distinct_pages(items: list[CollectionMember]) -> list[CollectionMember]:
    """Reject duplicate pages instead of native last-layer-wins replacement."""
    if len(items) != len({item.page_id for item in items}):
        msg = "Each page may appear only once in a collection."
        raise ValueError(msg)
    return items


Members = Annotated[list[CollectionMember], AfterValidator(distinct_pages)]


class CollectionSelection(Input):
    """Omitted selections preserve state; empty maps/lists explicitly clear it."""

    default_transcriptions: DefaultTranscriptions | None = None
    items: Members | None = None

    @model_validator(mode="after")
    def require_nonnull_selections(self) -> Self:
        """Keep omission distinct from unsupported null assignments."""
        values = {
            "default_transcriptions": self.default_transcriptions,
            "items": self.items,
        }
        if any(values[key] is None for key in self.model_fields_set & values.keys()):
            msg = "Collection selections cannot be null; use {} or [] to clear them."
            raise ValueError(msg)
        return self


class CollectionCreate(CollectionSelection):
    """Create a named collection with optional defaults and initial members."""

    name: RecordName


class CollectionPatch(CollectionSelection):
    """Edit metadata and optionally replace the entire collection membership."""

    name: RecordName | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        """Reject empty edits and null names before any network request."""
        if not self.model_fields_set or (
            "name" in self.model_fields_set and self.name is None
        ):
            msg = "Supply at least one collection change; name cannot be null."
            raise ValueError(msg)
        return self
