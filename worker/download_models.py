"""Typed private download actions and extensible native metadata."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConstrainedInt, ConstrainedStr, StrictStr


class Fingerprint(ConstrainedStr):
    """Native UUID hex identifier, never an arbitrary route component."""

    strict = True
    min_length = 32
    max_length = 32
    regex = re.compile(r"^[0-9a-f]{32}$")


class NonnegativeInteger(ConstrainedInt):
    """Server byte counts and collection counts without coercion."""

    strict = True
    ge = 0


class DownloadInput(BaseModel):
    """Reject fields outside the selected private operation."""

    operation: Literal["downloads"]

    class Config:
        """Private requests are immutable and closed."""

        frozen = True
        extra = "forbid"


class ListDownloads(DownloadInput):
    """Read the complete current-user download catalogue."""

    action: Literal["list"]


class DownloadDetail(DownloadInput):
    """Read or delete one owned download record."""

    action: Literal["get", "delete"]
    fingerprint: Fingerprint


class DownloadFile(DownloadInput):
    """Retrieve one generated file into a new local destination."""

    action: Literal["file"]
    fingerprint: Fingerprint
    destination: Path


class DownloadAction(BaseModel):
    """Select the action-specific private parser before doing any work."""

    action: Literal["list", "get", "delete", "file"]


class DownloadRecord(BaseModel):
    """Keep native metadata, including future fields, without trusting file URLs."""

    fingerprint: Fingerprint

    class Config:
        """Metadata is immutable but preserves native extension fields."""

        frozen = True
        extra = "allow"


class DownloadFileRecord(DownloadRecord):
    """Require the server-advertised size before retrieving file bytes."""

    file_size: NonnegativeInteger


class DownloadPage(BaseModel):
    """Native pagination envelope with extensible collection metadata."""

    count: NonnegativeInteger
    next: StrictStr | None
    previous: StrictStr | None = None
    results: list[DownloadRecord]

    class Config:
        """Preserve collection fields the connector does not know."""

        frozen = True
        extra = "allow"
