"""Generated-download identities, worker requests and report-filter evidence."""

from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.pagination import PageSelection

Fingerprint = Annotated[
    str, Field(strict=True, min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
]


class DownloadList(Input):
    """Read all generated downloads or one explicitly selected native page."""

    operation: Literal["downloads"] = "downloads"
    action: Literal["list"] = "list"
    pagination: PageSelection | None = None


class DownloadGet(Input):
    """Read owned metadata through a fixed fingerprint route."""

    operation: Literal["downloads"] = "downloads"
    action: Literal["get"] = "get"
    fingerprint: Fingerprint


class DownloadDelete(Input):
    """Delete one owned download through its native endpoint."""

    operation: Literal["downloads"] = "downloads"
    action: Literal["delete"] = "delete"
    fingerprint: Fingerprint


class DownloadFile(Input):
    """Save verified download bytes into a new MCP-host destination."""

    operation: Literal["downloads"] = "downloads"
    action: Literal["file"] = "file"
    fingerprint: Fingerprint
    destination: Path


class DownloadReportRecord(BaseModel):
    """Parse report linkage while retaining nullable and future metadata fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    fingerprint: Fingerprint
    task_report_id: Identifier | None = None

    def as_json(self) -> JsonValue:
        """Preserve upstream fields without adding omitted report linkage."""
        return TypeAdapter[JsonValue](JsonValue).validate_json(
            self.model_dump_json(exclude_unset=True)
        )


class DownloadReportPage(BaseModel):
    """Parse the combined worker result only when local filtering is requested."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    results: list[DownloadReportRecord]
