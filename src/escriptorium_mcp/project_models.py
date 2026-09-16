"""Project settings and native record-name and tag-assignment constraints."""

from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AnyUrl,
    Field,
    TypeAdapter,
    UrlConstraints,
    field_validator,
    model_validator,
)

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

RecordName = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
GuidelinesUrl = Annotated[
    AnyUrl,
    UrlConstraints(
        allowed_schemes=["http", "https", "ftp", "ftps"], host_required=True
    ),
]


def distinct_tags(values: list[Identifier]) -> list[Identifier]:
    """Reject accidental duplicate assignments before any server request."""
    if len(values) != len(set(values)):
        msg = "Tag IDs must be distinct."
        raise ValueError(msg)
    return values


TagIds = Annotated[list[Identifier], AfterValidator(distinct_tags)]


class ProjectCreateSettings(Input):
    """Optional guidelines, complete tag assignment and nullable presentation font."""

    guidelines: Annotated[str, Field(max_length=200)] | None = None
    tags: TagIds | None = None
    transcription_font: Identifier | None = None

    @field_validator("guidelines")
    @classmethod
    def check_guidelines(cls, value: str | None) -> str | None:
        """Keep blank/null clearing and preserve the caller's URL spelling."""
        if value:
            _ = TypeAdapter[GuidelinesUrl](GuidelinesUrl).validate_python(value)
        return value

    @model_validator(mode="after")
    def require_tags_when_supplied(self) -> Self:
        """Use an empty array to clear tags; null is not a native assignment."""
        if "tags" in self.model_fields_set and self.tags is None:
            msg = "Tags cannot be null; use [] to clear assignments."
            raise ValueError(msg)
        return self


class ProjectCreate(ProjectCreateSettings):
    """Private native create body without synthetic sharing defaults."""

    name: RecordName


class ProjectPatch(ProjectCreateSettings):
    """Change project fields; tags replace all personal-tag assignments."""

    name: RecordName | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        """Reject empty edits and explicitly null names before writing."""
        if not self.model_fields_set or (
            "name" in self.model_fields_set and self.name is None
        ):
            msg = "Supply a project change; name cannot be null."
            raise ValueError(msg)
        return self
