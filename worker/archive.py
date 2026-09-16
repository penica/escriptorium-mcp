"""Download complete available registers directly into the shared NAS archive."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlsplit

from escriptorium_connector import EscriptoriumConnector
from pydantic import BaseModel, Field, validator
from storage import books_root, portable_component, scan_filename


class ArchiveRequest(BaseModel):
    """Catalogue metadata naming a whole register in the configured archive."""

    operation: Literal["download_register"]
    document_id: int = Field(gt=0)
    parish: str = Field(regex=r"^[\w][\w .-]{0,99}$")
    register_id: str = Field(regex=r"^[0-9]{1,30}$")
    register_type: Literal[
        "Baptisms", "Marriages", "Deaths", "BaptismIndex", "MarriageIndex", "DeathIndex"
    ]
    years: str = Field(regex=r"^[0-9]{4}(?:-[0-9]{4})?$")

    _portable_parish = validator("parish", allow_reuse=True)(portable_component)

    class Config:
        """Keep private request fields strict and immutable."""

        frozen = True
        extra = "forbid"


class ArchiveError(ValueError):
    """Unsafe or inconsistent upstream archive metadata."""


class Image(BaseModel):
    """Original image location supplied by the page API."""

    uri: str


class Scan(BaseModel):
    """Available page metadata needed for the acquisition manifest."""

    pk: int = Field(gt=0)
    filename: str = ""
    source: str = ""
    image: Image | None = None


class ScanList(BaseModel):
    """One page of the API's register inventory."""

    count: int = Field(ge=0)
    next: str | None = None
    results: list[Scan]


class Entry(BaseModel):
    """Mutable progress record updated after each file is verified."""

    page_id: int
    original_filename: str
    source_url: str
    viewer_url: str
    image_url: str | None
    local_filename: str
    status: str = "pending"
    bytes: int = 0
    sha256: str | None = None


class Manifest(BaseModel):
    """Mutable acquisition ledger, separate from research completion."""

    document_id: int
    archive_directory: str
    manifest_path: str
    source_url: str
    viewer_url: str
    catalogue: ArchiveRequest
    started_at: str
    status: str = "partial"
    inventory_complete: bool = False
    listed_pages: int = 0
    available_scans: int = 0
    downloaded_scans: int = 0
    historical_missing_pages: str = (
        "unknown; the API inventory cannot establish historical completeness"
    )
    visual_inspection: str = "not performed"
    transcription: str = "not performed"
    files: list[Entry] = Field(default_factory=list)


def _same_origin(base: str, location: str) -> str:
    target = urljoin(base, location)
    origin, destination = urlsplit(base), urlsplit(target)
    if (
        destination.scheme not in {"http", "https"}
        or (origin.scheme, origin.hostname, origin.port)
        != (destination.scheme, destination.hostname, destination.port)
        or destination.username is not None
        or destination.password is not None
    ):
        message = "Archive URLs must use the configured eScriptorium origin"
        raise ArchiveError(message)
    return target


def _inventory(client: EscriptoriumConnector, url: str) -> list[Scan]:
    scans: list[Scan] = []
    visited: set[str] = set()
    next_url: str | None = url
    count: int | None = None
    while next_url:
        current = _same_origin(client.base_url, next_url)
        if current in visited:
            message = "Repeated pagination URL"
            raise ArchiveError(message)
        visited.add(current)
        with client.http.get(current, allow_redirects=False) as response:
            if response.is_redirect:
                message = "Redirected API inventory is not accepted"
                raise ArchiveError(message)
            response.raise_for_status()
            page = ScanList.parse_raw(response.content)
        if count is not None and count != page.count:
            message = "Register inventory changed while listing pages"
            raise ArchiveError(message)
        count = page.count
        scans.extend(page.results)
        next_url = urljoin(current, page.next) if page.next else None
    if len(scans) != count or len({scan.pk for scan in scans}) != len(scans):
        message = "Incomplete or duplicate register inventory"
        raise ArchiveError(message)
    return scans


def _save_manifest(folder: Path, manifest: Manifest) -> None:
    temporary = folder / "manifest.json.part"
    temporary.write_text(manifest.json(indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(folder / "manifest.json")


def _download(client: EscriptoriumConnector, folder: Path, entry: Entry) -> None:
    if entry.image_url is None:
        entry.status = "no_scan_available"
        return
    temporary = folder / f"{entry.local_filename}.part"
    with client.http.get(
        entry.image_url,
        stream=True,
        allow_redirects=False,
        headers={"Accept": "*/*", "Accept-Encoding": "identity"},
    ) as response:
        if response.is_redirect:
            message = "Redirected media is not accepted"
            raise ArchiveError(message)
        response.raise_for_status()
        with temporary.open("xb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                _ = output.write(chunk)
        entry.bytes = temporary.stat().st_size
        expected = response.headers.get("Content-Length")
        if (
            expected is not None
            and not response.headers.get("Content-Encoding")
            and entry.bytes != int(expected)
        ):
            message = "Downloaded scan byte count differs from Content-Length"
            raise ArchiveError(message)
    with temporary.open("rb") as downloaded:
        entry.sha256 = hashlib.file_digest(downloaded, "sha256").hexdigest()
    temporary.replace(folder / entry.local_filename)
    entry.status = "downloaded_verified"


def download_register(
    client: EscriptoriumConnector,
    request: ArchiveRequest,
    *,
    root: Path | None = None,
) -> str:
    """Acquire every available original image; never stage scans on the local disk."""
    root = root if root is not None else books_root()
    if root is None or not root.is_absolute() or not root.is_dir():
        message = (
            "Set ESCRIPTORIUM_BOOKS_ROOT to an existing mounted absolute archive path"
        )
        raise ArchiveError(message)
    parish = root / request.parish
    if parish.is_symlink():
        message = "Parish destination must not be a symbolic link"
        raise ArchiveError(message)
    parish.mkdir(exist_ok=True)
    folder = parish / f"{request.register_id}_{request.register_type}_{request.years}"
    folder.mkdir(exist_ok=False)
    source = f"{client.api_url}documents/{request.document_id}/parts/"
    viewer = f"{client.base_url}document/{request.document_id}/"
    manifest = Manifest(
        document_id=request.document_id,
        archive_directory=str(folder),
        manifest_path=str(folder / "manifest.json"),
        source_url=source,
        viewer_url=viewer,
        catalogue=request,
        started_at=datetime.now(UTC).isoformat(),
    )
    _save_manifest(folder, manifest)
    scans = _inventory(client, source)
    manifest.listed_pages = len(scans)
    for scan in scans:
        image_url = (
            _same_origin(client.base_url, scan.image.uri) if scan.image else None
        )
        original = scan.filename or (
            unquote(urlsplit(image_url).path).rsplit("/", 1)[-1]
            if image_url
            else "scan"
        )
        safe = scan_filename(original)
        manifest.files.append(
            Entry(
                page_id=scan.pk,
                original_filename=original,
                source_url=scan.source or source,
                viewer_url=f"{viewer}part/{scan.pk}/edit/",
                image_url=image_url,
                local_filename=f"{scan.pk}_{safe}",
            )
        )
    manifest.inventory_complete = True
    manifest.available_scans = sum(
        entry.image_url is not None for entry in manifest.files
    )
    _save_manifest(folder, manifest)
    for entry in manifest.files:
        _download(client, folder, entry)
        manifest.downloaded_scans += int(entry.status == "downloaded_verified")
        _save_manifest(folder, manifest)
    manifest.status = "complete_available_scans"
    _save_manifest(folder, manifest)
    return manifest.json(ensure_ascii=False)
