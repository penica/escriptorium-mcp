"""Scoped metadata associations and deliberately separate global key edits."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

MetadataName = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
MetadataValue = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
CidocId = Annotated[str, Field(max_length=8)]


class DocumentMetadataTarget(Input):
    """Metadata associations belonging to one readable document."""

    scope: Literal["document"]
    document_id: Identifier


class PageMetadataTarget(Input):
    """Metadata associations for a page checked within its parent document."""

    scope: Literal["page"]
    document_id: Identifier
    page_id: Identifier


MetadataTarget = Annotated[
    DocumentMetadataTarget | PageMetadataTarget, Field(discriminator="scope")
]


class MetadataKey(Input):
    """Native shared key selection; omitted CIDOC differs from explicit null."""

    name: MetadataName
    cidoc_id: CidocId | None = None


class MetadataCreate(Input):
    """Create an association, allowing native duplicate rows without upserting."""

    key: MetadataKey
    value: MetadataValue


class MetadataValuePatch(Input):
    """Change only this association's value, without editing its global key."""

    value: MetadataValue


class SharedMetadataKeyPatch(Input):
    """Changes to a global definition, affecting every association using it."""

    name: MetadataName | None = None
    cidoc_id: CidocId | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        """Keep omission distinct from clearing nullable CIDOC or invalid key names."""
        if not self.model_fields_set:
            msg = "Supply a shared key name or cidoc_id change."
            raise ValueError(msg)
        if "name" in self.model_fields_set and self.name is None:
            msg = "A metadata key name cannot be null."
            raise ValueError(msg)
        return self


class SharedMetadataKeyUpdate(Input):
    """The native nested PATCH excludes value to avoid combined partial updates."""

    key: SharedMetadataKeyPatch
