"""Typed document annotation ontology definitions."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.record_models import Patch

ComponentName = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
ComponentValue = Annotated[str, Field(max_length=128)]
MarkerType = Literal[
    "Rectangle", "Polygon", "Background Color", "Text Color", "Bold", "Italic"
]


class AnnotationComponent(Input):
    """Named input field; an empty allowed-values list permits free text."""

    name: ComponentName
    allowed_values: list[ComponentValue] | None = Field(default_factory=list)


class AnnotationComponentPatch(Patch):
    """Change a component label or replace its allowed values."""

    name: ComponentName | None = None
    allowed_values: list[ComponentValue] | None = Field(default_factory=list)

    @model_validator(mode="after")
    def require_nonnull_name(self) -> Self:
        """Reject an explicit null label while allowing an omitted label."""
        if "name" in self.model_fields_set and self.name is None:
            msg = "Component name cannot be null."
            raise ValueError(msg)
        return self


class AnnotationType(Input):
    """An annotation type is resolved or created by its global name."""

    name: ComponentName


class AnnotationTaxonomy(Input):
    """Complete annotation display definition with document component IDs."""

    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"\S")]
    marker_type: MarkerType
    abbreviation: Annotated[str, Field(max_length=3)] | None = ""
    marker_detail: Annotated[str, Field(max_length=7)] | None = ""
    has_comments: bool = False
    typology: AnnotationType | None = None
    components: list[Identifier] = Field(default_factory=list)


class AnnotationTaxonomyReplacement(AnnotationTaxonomy):
    """Require explicit relations because the upstream PATCH replaces them."""

    typology: AnnotationType | None = Field(...)
    components: list[Identifier] = Field(...)
