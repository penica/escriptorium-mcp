"""Inputs for documents, page metadata and transcription text."""

from typing import Annotated, Literal, Self

from pydantic import Field, FilePath, FiniteFloat, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier, Name
from escriptorium_mcp.project_models import RecordName, TagIds
from escriptorium_mcp.text_models import CharacterGraph, Score, TextChanges


class DocumentCreate(Input):
    """Create a document in a project identified by slug."""

    name: RecordName
    project: Name
    main_script: Name
    read_direction: Literal["ltr", "rtl"] = "ltr"
    line_offset: Literal[0, 1, 2] = 0
    show_confidence_viz: bool = False
    tags: TagIds = Field(default_factory=list)
    transcription_font: Identifier | None = None


class Patch(Input):
    """Require at least one deliberately supplied metadata change."""

    @model_validator(mode="after")
    def require_change(self) -> Self:
        """Reject empty PATCH requests."""
        if not self.model_fields_set:
            msg = "Supply at least one field to update."
            raise ValueError(msg)
        return self


class DocumentPatch(Patch):
    """Rename, move project, or change document reading conventions."""

    name: RecordName | None = None
    project: Name | None = None
    main_script: Name | None = None
    read_direction: Literal["ltr", "rtl"] | None = None
    line_offset: Literal[0, 1, 2] | None = None
    show_confidence_viz: bool | None = None
    tags: TagIds | None = None
    transcription_font: Identifier | None = None

    @model_validator(mode="after")
    def require_nonnull_changes(self) -> Self:
        """Reject null for required settings while allowing a font override to clear."""
        values = {
            "name": self.name,
            "project": self.project,
            "main_script": self.main_script,
            "read_direction": self.read_direction,
            "line_offset": self.line_offset,
            "show_confidence_viz": self.show_confidence_viz,
            "tags": self.tags,
        }
        if any(
            values[field] is None for field in self.model_fields_set & values.keys()
        ):
            msg = (
                "Only transcription_font may be null; "
                "omit other fields to preserve them."
            )
            raise ValueError(msg)
        return self


class PagePatch(Patch):
    """Editable page metadata; ordering uses the move tool."""

    name: Annotated[str, Field(max_length=512)] | None = None
    source: Annotated[str, Field(max_length=1024)] | None = None
    comments: str | None = None
    typology: Identifier | None = None
    original_filename: Annotated[str, Field(max_length=1024)] | None = None
    max_avg_confidence: FiniteFloat | None = None

    @model_validator(mode="after")
    def require_nonnull_labels(self) -> Self:
        """Preserve omission while rejecting null for non-nullable server fields."""
        labels = {
            "name": self.name,
            "source": self.source,
            "original_filename": self.original_filename,
        }
        if any(
            labels[field] is None for field in self.model_fields_set & labels.keys()
        ):
            msg = "Page name, source and original_filename cannot be null."
            raise ValueError(msg)
        return self


class PageUpload(Input):
    """Upload an existing image from this machine or a mounted volume."""

    image_path: FilePath
    name: Annotated[str, Field(max_length=512)] = ""
    source: Annotated[str, Field(max_length=1024)] = ""


class PageMetadata(Input):
    """Multipart metadata for a page image."""

    name: str
    source: str


class Rename(Input):
    """A new project display name."""

    name: RecordName


class LineText(Input):
    """A line's text in a particular transcription layer."""

    line: Identifier
    transcription: Identifier
    content: Annotated[str, Field(max_length=2048)]
    graphs: list[CharacterGraph] | None = None
    avg_confidence: Score | None = None


class TextPatch(TextChanges):
    """Edit text, character graphs, confidence or scoped line/layer references."""
