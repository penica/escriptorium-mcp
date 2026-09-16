"""Witness inputs and tolerant native metadata used for ownership diagnosis."""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    FilePath,
    JsonValue,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

WitnessName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
]


def require_acknowledgment(value: StrictBool) -> bool:
    """Require actual JSON true for the known native ownership uncertainty."""
    if not value:
        msg = "Explicitly acknowledge unverified native witness ownership with true."
        raise ValueError(msg)
    return value


OwnershipAcknowledgment = Annotated[
    StrictBool,
    AfterValidator(require_acknowledgment),
    Field(json_schema_extra={"const": True}),
]


class WitnessUpload(Input):
    """Upload text once, acknowledging that native creation may leave no owner."""

    name: WitnessName
    file_path: FilePath
    acknowledge_unverified_ownership: OwnershipAcknowledgment


class WitnessPatch(Input):
    """Rename or replace an owned witness; omitted fields remain unchanged."""

    name: WitnessName | None = None
    file_path: FilePath | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        """Reject empty changes and null values for required native fields."""
        values = {"name": self.name, "file_path": self.file_path}
        if not self.model_fields_set or any(
            values[field] is None for field in self.model_fields_set
        ):
            msg = "Supply name or file_path; witness changes cannot be null."
            raise ValueError(msg)
        return self


class WitnessIdentity(BaseModel):
    """Validate native pk without requiring unrelated metadata."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    pk: Identifier


class WitnessRecord(WitnessIdentity):
    """Parse optional ownership/file metadata without coercing invalid values."""

    owner: StrictStr | None = None
    file: StrictStr | None = None


class OwnershipReadback(Input):
    """Keep accepted creation distinct from the evidence of current ownership."""

    status: Literal["verified", "unverified", "unavailable"]
    reason: (
        Literal[
            "missing_owner",
            "owner_mismatch",
            "identity_mismatch",
            "invalid_create_metadata",
            "invalid_readback_metadata",
            "missing_identity",
            "readback_failed",
        ]
        | None
    )
    witness_id: Identifier | None
    record: JsonValue = None
    error: str | None = None
