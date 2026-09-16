"""Exactly one source and coherent target options for native document imports."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, FilePath, HttpUrl, field_validator, model_validator

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

ImportName = Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]


class PdfFile(Input):
    """A PDF on the MCP host; the server imports page images only."""

    kind: Literal["pdf_file"]
    file_path: FilePath

    @field_validator("file_path")
    @classmethod
    def require_pdf(cls, value: Path) -> Path:
        """Keep the explicit PDF mode consistent with native extension dispatch."""
        if value.suffix != ".pdf":
            msg = "PDF mode requires a lowercase .pdf file extension."
            raise ValueError(msg)
        return value


class XmlUpload(Input):
    """Existing XML/ZIP source on the MCP host; content is parsed server-side."""

    file_path: FilePath

    @field_validator("file_path")
    @classmethod
    def require_xml_or_zip(cls, value: Path) -> Path:
        """Avoid modes whose file extension selects a different native parser."""
        if value.suffix not in {".xml", ".zip"}:
            msg = "XML and METS file modes require a lowercase .xml or .zip extension."
            raise ValueError(msg)
        return value


class TextImportOptions(Input):
    """Optional native layer name, or METS layer-name prefix, and override."""

    name: ImportName | None = None
    override: bool = False

    @model_validator(mode="after")
    def require_name_if_supplied(self) -> Self:
        """Omit unused options instead of sending null to the native serializer."""
        if "name" in self.model_fields_set and self.name is None:
            msg = "Omit unused name instead of passing null."
            raise ValueError(msg)
        return self


class XmlFile(TextImportOptions, XmlUpload):
    """ALTO/PAGE XML or ordinary ZIP, optionally targeting a document layer."""

    kind: Literal["xml_file"]
    transcription_id: Identifier | None = None

    @model_validator(mode="after")
    def require_one_target(self) -> Self:
        """Prevent silently prioritizing a name over the supplied layer ID."""
        if "transcription_id" in self.model_fields_set and (
            self.transcription_id is None or self.name is not None
        ):
            msg = "Supply either name or transcription_id; omit unused options."
            raise ValueError(msg)
        return self


class IiifUrl(Input):
    """Presentation 2 manifest fetched by eScriptorium, importing all canvases."""

    kind: Literal["iiif_url"]
    url: HttpUrl


class MetsOptions(TextImportOptions):
    """METS creates prefixed source layers rather than targeting one exact layer."""

    prefix_transcription_id: Identifier | None = None

    @model_validator(mode="after")
    def require_one_prefix(self) -> Self:
        """Select a layer-name prefix without silently overriding an explicit name."""
        if "prefix_transcription_id" in self.model_fields_set and (
            self.prefix_transcription_id is None or self.name is not None
        ):
            msg = "Supply either name or prefix_transcription_id; omit unused options."
            raise ValueError(msg)
        return self


class MetsFile(MetsOptions, XmlUpload):
    """METS descriptor with absolute references, or a self-contained METS ZIP."""

    kind: Literal["mets_file"]


class MetsUrl(MetsOptions):
    """METS descriptor fetched by eScriptorium; relative references use its URL."""

    kind: Literal["mets_url"]
    url: HttpUrl


ImportSource = Annotated[
    PdfFile | XmlFile | IiifUrl | MetsFile | MetsUrl, Field(discriminator="kind")
]
