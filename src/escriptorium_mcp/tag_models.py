"""Scope and editable fields for personal and project tag definitions."""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

TagName = Annotated[
    str, Field(strict=True, min_length=1, max_length=100, pattern=r"\S")
]
TagColor = Annotated[str, Field(strict=True, min_length=1, max_length=7, pattern=r"\S")]


class PersonalProjectTags(Input):
    """Select the authenticated user's personal definitions for tagging projects."""

    scope: Literal["personal_projects"]


class ProjectDocumentTags(Input):
    """Select definitions shared by documents within a single project."""

    scope: Literal["project_documents"]
    project_id: Identifier


TagTarget = Annotated[
    PersonalProjectTags | ProjectDocumentTags, Field(discriminator="scope")
]


class TagCreate(Input):
    """Omit color to retain the server's generated default."""

    name: TagName
    color: TagColor | None = None

    @model_validator(mode="after")
    def require_supplied_color(self) -> Self:
        """Distinguish omitted default color from unsupported explicit null."""
        if "color" in self.model_fields_set and self.color is None:
            msg = "Tag color cannot be null; omit it to use the server default."
            raise ValueError(msg)
        return self


class TagPatch(Input):
    """Edit a definition without accepting empty or explicitly null changes."""

    name: TagName | None = None
    color: TagColor | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        """Preserve omitted fields while rejecting null for native required fields."""
        if not self.model_fields_set:
            msg = "Supply at least one tag field to update."
            raise ValueError(msg)
        values = {"name": self.name, "color": self.color}
        if any(values[field] is None for field in self.model_fields_set):
            msg = "Tag name and color cannot be null."
            raise ValueError(msg)
        return self


class TagProjectIdentity(BaseModel):
    """Project responses identify their parent with id rather than pk."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    id: Identifier


class TagIdentity(BaseModel):
    """Require the requested row identity without discarding the raw response."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    pk: Identifier
