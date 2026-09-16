"""Ontology inputs and tolerant read models for old and current eScriptorium."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

TypeKind = Literal["block", "line", "part", "annotations"]
ContentKind = Literal["block", "line", "part"]
TypeName = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]


class TypeDefinition(Input):
    """Name supported by both legacy and current ontology APIs."""

    name: TypeName
    color: Annotated[str, Field(max_length=7)] | None = None


class OntologyType(BaseModel):
    """A type returned in a document's ontology."""

    pk: Identifier
    name: str
    color: str | None = None


class DocumentOntology(BaseModel):
    """Document-local allowed type lists; global catalogues may omit these IDs."""

    valid_block_types: list[OntologyType]
    valid_line_types: list[OntologyType]
    valid_part_types: list[OntologyType]

    def types(self, kind: ContentKind) -> list[OntologyType]:
        """Select the allowed types for a content category."""
        return {
            "part": self.valid_part_types,
            "block": self.valid_block_types,
            "line": self.valid_line_types,
        }[kind]


class OntologySelection(Input):
    """Replacement lists: omitted categories stay unchanged, empty lists clear."""

    valid_block_types: list[Identifier] = Field(default_factory=list)
    valid_line_types: list[Identifier] = Field(default_factory=list)
    valid_part_types: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_lists(self) -> Self:
        """Reject absent intent and duplicate IDs before reaching the server."""
        if not self.model_fields_set:
            msg = "Supply at least one type list."
            raise ValueError(msg)
        for field in self.model_fields_set:
            values = {
                "valid_block_types": self.valid_block_types,
                "valid_line_types": self.valid_line_types,
                "valid_part_types": self.valid_part_types,
            }[field]
            if len(values) != len(set(values)):
                msg = "Type lists must not contain duplicate IDs."
                raise ValueError(msg)
        return self


class TypeReplacement(Input):
    """Preview or apply a document-wide type replacement; null means untyped."""

    kind: ContentKind
    source_type_id: Identifier | None
    target_type_id: Identifier | None
    apply: bool = False
    remove_source_from_ontology: bool = False

    @model_validator(mode="after")
    def check_replacement(self) -> Self:
        """Reject nonsensical replacement requests."""
        if self.source_type_id == self.target_type_id:
            msg = "Source and target type must differ."
            raise ValueError(msg)
        if self.remove_source_from_ontology and self.source_type_id is None:
            msg = "An untyped source cannot be removed from the ontology."
            raise ValueError(msg)
        return self
