"""Validated transcription edits and character geometry."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

Content = Annotated[str, Field(max_length=2048)]
LayerName = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
Character = Annotated[str, Field(min_length=1, max_length=1)]
Score = Annotated[float, Field(allow_inf_nan=False)]
GraphPoint = Annotated[list[Score], Field(min_length=2, max_length=2)]
GraphPolygon = Annotated[list[GraphPoint], Field(min_length=3)]


class CharacterGraph(Input):
    """Optional character, polygon and confidence fields from the server schema."""

    c: Character | None = None
    poly: GraphPolygon | None = None
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def reject_null_properties(self) -> Self:
        """Allow missing graph properties but reject explicit null values."""
        if any(getattr(self, field) is None for field in self.model_fields_set):
            msg = "Omit absent graph properties instead of setting them to null."
            raise ValueError(msg)
        return self


class TextChanges(Input):
    """Partial edits preserve omitted fields; null clears graphs or confidence."""

    content: Content | None = None
    line: Identifier | None = None
    transcription: Identifier | None = None
    graphs: list[CharacterGraph] | None = None
    avg_confidence: Score | None = None

    @model_validator(mode="after")
    def require_valid_change(self) -> Self:
        """Require an edit beyond the bulk record ID and reject null required fields."""
        if not self.model_fields_set - {"pk"}:
            msg = "Supply at least one transcription field to update."
            raise ValueError(msg)
        for field in self.model_fields_set & {"content", "line", "transcription"}:
            if getattr(self, field) is None:
                msg = f"{field} cannot be null; omit it to preserve its value."
                raise ValueError(msg)
        return self


class BulkTextPatch(TextChanges):
    """One existing line-transcription record in a bulk update."""

    pk: Identifier


class LayerPatch(Input):
    """Editable layer settings; archived layers retain their line records."""

    name: LayerName | None = None
    archived: bool | None = None
    avg_confidence: Score | None = None
    comments: str | None = None

    @model_validator(mode="after")
    def require_valid_change(self) -> Self:
        """Require an edit and keep name/archived non-null."""
        if not self.model_fields_set:
            msg = "Supply at least one layer field to update."
            raise ValueError(msg)
        for field in self.model_fields_set & {"name", "archived"}:
            if getattr(self, field) is None:
                msg = f"{field} cannot be null."
                raise ValueError(msg)
        return self
