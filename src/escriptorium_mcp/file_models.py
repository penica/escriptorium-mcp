"""Local file transfers and full-register acquisition metadata."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, FilePath, HttpUrl

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
    """Native eScriptorium export job; download arrives through its notification."""

    transcription: Identifier
    file_format: Literal["alto", "pagexml", "text"] = "alto"
    parts: Parts | None = None
    region_types: list[int | Literal["Undefined", "Orphan"]] | None = None
    include_characters: bool = False


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
