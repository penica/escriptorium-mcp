"""Model metadata inputs and tolerant model/version read contracts."""

from typing import Annotated, ClassVar, Literal, Self, assert_never

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_serializer,
    model_validator,
)

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

ModelJob = Literal[1, 2]
JobLabel = Literal["Segment", "Recognize"]
ModelName = Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
Revision = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]


def job_label(job: ModelJob) -> JobLabel:
    """DisplayChoiceField writes require labels, while filters require numbers."""
    match job:
        case 1:
            return "Segment"
        case 2:
            return "Recognize"
        case _:
            assert_never(job)


class ModelUpdate(Input):
    """Omit unchanged fields; these metadata fields cannot be cleared with null."""

    name: ModelName | None = None
    job: ModelJob | None = None
    file_size: Annotated[int, Field(ge=0, strict=True)] | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        """Reject empty edits and explicit nulls before any HTTP request."""
        values = {"name": self.name, "job": self.job, "file_size": self.file_size}
        if not self.model_fields_set or any(
            values[key] is None for key in self.model_fields_set
        ):
            message = (
                "Supply at least one metadata field; explicit null is unsupported."
            )
            raise ValueError(message)
        return self

    @field_serializer("job")
    def serialize_job(self, value: ModelJob | None) -> JobLabel | None:
        """Translate the public numeric input only at the API write boundary."""
        return job_label(value) if value is not None else None


class VersionData(BaseModel):
    """Parse the storage reference while preserving server-specific metrics."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    file: str | None = None


class VersionRecord(BaseModel):
    """Preserve arbitrary checkpoint metrics returned by custom server versions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    revision: str
    data: VersionData

    def as_json(self) -> JsonValue:
        """Return server fields without reducing checkpoint metadata."""
        return TypeAdapter[JsonValue](JsonValue).validate_json(
            self.model_dump_json(exclude_unset=True)
        )


class ModelRecord(BaseModel):
    """Only fields needed for permissions, association reads and downloads."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    pk: Identifier
    file: str | None = None
    rights: str | None = None
    training: bool | None = None
    documents: list[Identifier] = Field(default_factory=list)
    versions: list[VersionRecord] = Field(default_factory=list)


class ReplacementMetadata(Input):
    """Keep upstream storage accounting consistent with replacement bytes."""

    file_size: Annotated[int, Field(ge=0)]
