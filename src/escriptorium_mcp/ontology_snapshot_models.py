"""Portable schema-only snapshots with names replacing server-specific IDs."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from escriptorium_mcp.annotation_models import AnnotationComponent, MarkerType
from escriptorium_mcp.api import Input
from escriptorium_mcp.ontology_models import ContentKind, TypeName


class SnapshotType(Input):
    """Portable document type definition."""

    name: TypeName
    color: Annotated[str, Field(max_length=7)] | None = None


class SnapshotTaxonomy(Input):
    """Annotation display settings with component and typology names."""

    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"\S")]
    marker_type: MarkerType
    abbreviation: Annotated[str, Field(max_length=3)] | None = ""
    marker_detail: Annotated[str, Field(max_length=7)] | None = ""
    has_comments: bool = False
    typology: TypeName | None = None
    components: list[TypeName] = Field(default_factory=list)


class OntologySnapshot(Input):
    """Versioned schema; excludes annotation instances, text and geometry."""

    format: Literal["escriptorium-ontology"] = "escriptorium-ontology"
    version: Literal[1] = 1
    scope: Literal["schema-only"] = "schema-only"
    valid_block_types: list[SnapshotType]
    valid_line_types: list[SnapshotType]
    valid_part_types: list[SnapshotType]
    components: list[AnnotationComponent]
    taxonomies: list[SnapshotTaxonomy]

    def types(self, kind: ContentKind) -> list[SnapshotType]:
        """Select one document type category."""
        return {
            "block": self.valid_block_types,
            "line": self.valid_line_types,
            "part": self.valid_part_types,
        }[kind]

    @model_validator(mode="after")
    def check_references(self) -> Self:
        """Reject ambiguous names and unresolved component references."""
        groups = [
            self.valid_block_types,
            self.valid_line_types,
            self.valid_part_types,
            self.components,
            self.taxonomies,
        ]
        for group in groups:
            names = [item.name for item in group]
            if len(names) != len(set(names)):
                msg = "Snapshot names must be unique within each category."
                raise ValueError(msg)
        components = {item.name for item in self.components}
        for taxonomy in self.taxonomies:
            if len(taxonomy.components) != len(set(taxonomy.components)):
                msg = "Taxonomy component references must be unique."
                raise ValueError(msg)
            if not set(taxonomy.components) <= components:
                msg = "Taxonomy references an undefined snapshot component."
                raise ValueError(msg)
        return self
