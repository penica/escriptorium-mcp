"""Coherent witness/search choices and explicit target reuse for native alignment."""

from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    FilePath,
    FiniteFloat,
    StringConstraints,
    model_validator,
)

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.job_models import Parts

LayerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)
]
RegionSelection = Annotated[
    list[Identifier | Literal["Undefined", "Orphan"]], Field(min_length=1)
]


class ExistingWitness(Input):
    """Reuse a textual witness visible through the current user's owned route."""

    kind: Literal["existing"]
    witness_id: Identifier


class UploadedWitness(Input):
    """Upload UTF-8 text directly in alignment, preserving original file bytes."""

    kind: Literal["file"]
    file_path: FilePath


AlignmentWitness = Annotated[
    ExistingWitness | UploadedWitness, Field(discriminator="kind")
]


class BeamSearch(Input):
    """Beam search explicitly disables max-offset search in the native request."""

    kind: Literal["beam"]
    beam_size: Annotated[int, Field(strict=True, ge=1, le=100)] = 20


class OffsetSearch(Input):
    """Offset search explicitly disables native default beam search, including zero."""

    kind: Literal["offset"]
    max_offset: Annotated[int, Field(strict=True, ge=0, le=80)]


AlignmentSearch = Annotated[BeamSearch | OffsetSearch, Field(discriminator="kind")]


class AlignmentParts(Input):
    """Omission selects all pages; a supplied list must be nonempty and distinct."""

    parts: Parts | None = None

    @model_validator(mode="after")
    def require_selected_parts(self) -> Self:
        """Do not let null or duplicate selections change the intended page scope."""
        if "parts" in self.model_fields_set and self.parts is None:
            msg = "Omit parts for all pages instead of passing null."
            raise ValueError(msg)
        if self.parts is not None and len(set(self.parts)) != len(self.parts):
            msg = "Alignment pages must be distinct."
            raise ValueError(msg)
        return self


class AlignmentJob(AlignmentParts):
    """Reference-text alignment may reuse text in existing or hidden target layers."""

    transcription: Identifier
    witness: AlignmentWitness
    layer_name: LayerName
    acknowledge_target_reuse: Annotated[
        bool, Field(strict=True, json_schema_extra={"const": True})
    ]
    region_types: RegionSelection | None = None
    n_gram: Annotated[int, Field(strict=True, ge=2, le=25)] = 25
    gap: Annotated[int, Field(strict=True, ge=1, le=1000000)] = 600
    threshold: Annotated[FiniteFloat, Field(strict=True, ge=0, le=1)] = 0.8
    merge: bool = False
    add_hyphens: bool = False
    full_doc: bool = True
    search: AlignmentSearch = Field(default_factory=lambda: BeamSearch(kind="beam"))

    @model_validator(mode="after")
    def require_acknowledged_scope(self) -> Self:
        """Require explicit reuse acknowledgment and preserve intended region scope."""
        if self.acknowledge_target_reuse is not True:
            msg = "acknowledge_target_reuse must be true."
            raise ValueError(msg)
        if "region_types" in self.model_fields_set and self.region_types is None:
            msg = "Omit region_types for all types instead of passing null."
            raise ValueError(msg)
        if self.region_types is not None and len(set(self.region_types)) != len(
            self.region_types
        ):
            msg = "Alignment region types must be distinct."
            raise ValueError(msg)
        return self


class ForcedAlignmentJob(AlignmentParts):
    """Replace character graphs in the specified layer using a readable model."""

    model: Identifier
    transcription: Identifier


class NativeAlignment(Input):
    """Explicit native defaults without public acknowledgments or variant wrappers."""

    transcription: Identifier
    existing_witness: Identifier | None = None
    parts: Parts | None = None
    layer_name: LayerName
    region_types: list[str]
    n_gram: int
    gap: int
    threshold: float
    merge: bool
    add_hyphens: bool
    full_doc: bool
    beam_size: int
    max_offset: int
