"""Local file transfers and full-register acquisition metadata."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, FilePath, HttpUrl, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier, Name
from escriptorium_mcp.job_models import Parts


class RegisterDownload(Input):
    """Catalogue identifiers used for the fixed NAS book folder."""

    operation: Literal["download_register"] = "download_register"
    document_id: Identifier
    parish: Annotated[str, Field(pattern=r"^[\w][\w .-]{0,99}$")]
    register_id: Annotated[str, Field(pattern=r"^[0-9]{1,30}$")]
    register_type: Literal[
        "Baptisms",
        "Marriages",
        "Deaths",
        "BaptismIndex",
        "MarriageIndex",
        "DeathIndex",
    ]
    years: Annotated[str, Field(pattern=r"^[0-9]{4}(?:-[0-9]{4})?$")]


class TranscriptionExport(Input):
    """Export a layer to a new local file, all pages unless explicitly selected."""

    operation: Literal["export_transcriptions"] = "export_transcriptions"
    document_id: Identifier
    transcription_id: Identifier
    destination: Path
    file_format: Literal["text", "json"] = "text"
    parts: Parts | None = None


class ServerExport(Input):
    """Native export options; JSON-only settings require the JSON archive format."""

    transcription: Identifier
    file_format: Literal[
        "alto", "pagexml", "text", "json", "openitimarkdown", "teixml"
    ] = "alto"
    parts: Parts | None = None
    region_types: (
        Annotated[
            list[Identifier | Literal["Undefined", "Orphan"]], Field(min_length=1)
        ]
        | None
    ) = None
    include_characters: bool = False
    include_images: bool = False
    include_metadata: bool = False
    include_models: bool = False
    all_transcriptions: bool = False
    include_annotations: bool = False
    anonymize: bool = False
    archive_format: Literal["zip", "tar.gz"] = "zip"

    @model_validator(mode="after")
    def require_distinct_selections(self) -> Self:
        """Keep an explicit selection distinct from the omitted all-pages scope."""
        if self.parts is not None and len(set(self.parts)) != len(self.parts):
            msg = "Export pages must be distinct."
            raise ValueError(msg)
        if self.region_types is not None and len(set(self.region_types)) != len(
            self.region_types
        ):
            msg = "Export region types must be distinct."
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def require_supported_options(self) -> Self:
        """Reject newly exposed options when the chosen exporter ignores them."""
        if self.file_format != "json" and (
            self.include_metadata
            or self.include_models
            or self.all_transcriptions
            or self.include_annotations
            or self.anonymize
            or "archive_format" in self.model_fields_set
        ):
            msg = (
                "Metadata, models, all layers, annotations, anonymize and "
                "archive_format require JSON."
            )
            raise ValueError(msg)
        if self.include_images and self.file_format not in {"alto", "pagexml", "json"}:
            msg = "Image inclusion requires ALTO, PAGE XML or JSON."
            raise ValueError(msg)
        return self


class DocumentImport(Input):
    """Import a supported PDF, image archive or transcription file."""

    file_path: FilePath
    name: Name
    override: bool = False


class ImportMetadata(Input):
    """Fields passed to eScriptorium's import form."""

    name: Name
    override: bool


class ExportDownload(Input):
    """Download an export URL supplied by an eScriptorium notification."""

    operation: Literal["download_export"] = "download_export"
    url: HttpUrl
    destination: Path
