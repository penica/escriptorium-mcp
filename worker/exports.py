"""Direct transcription exports and authenticated export-file retrieval."""

import hashlib
import json
from pathlib import Path
from typing import Literal, assert_never

from escriptorium_connector import EscriptoriumConnector
from pydantic import BaseModel, Field
from rest import ApiRequest, execute_api, same_origin
from storage import books_root, finish_file, portable_component


class ExportRequest(BaseModel):
    """Direct textual export, independent of server-side download notifications."""

    operation: Literal["export_transcriptions"]
    document_id: int = Field(gt=0)
    transcription_id: int = Field(gt=0)
    destination: Path
    file_format: Literal["text", "json"] = "text"
    parts: list[int] | None = None


class DownloadRequest(BaseModel):
    """A completed export link on the configured server."""

    operation: Literal["download_export"]
    url: str
    destination: Path


def destination_path(path: Path) -> Path:
    """Keep research exports outside the scan-only Books archive."""
    destination = path.expanduser().resolve()
    root = books_root()
    _ = portable_component(destination.name)
    if root is not None and destination.is_relative_to(root):
        msg = "Save transcription exports outside the NAS Books archive."
        raise ValueError(msg)
    if (
        destination.exists()
        or destination.with_name(destination.name + ".part").exists()
    ):
        msg = "Export destination or partial file already exists."
        raise FileExistsError(msg)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def completed_file(path: Path) -> str:
    """Return verifiable file metadata without returning its private contents."""
    with path.open("rb") as output:
        checksum = hashlib.file_digest(output, "sha256").hexdigest()
    return json.dumps(
        {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": checksum,
            "status": "complete",
        }
    )


def export_transcriptions(client: EscriptoriumConnector, request: ExportRequest) -> str:
    """Export line records from one verified transcription layer in reading order."""
    base = f"documents/{request.document_id}/"
    _ = execute_api(
        client,
        ApiRequest(
            operation="api",
            method="GET",
            route=f"{base}transcriptions/{request.transcription_id}/",
        ),
    )
    pages = json.loads(
        execute_api(
            client,
            ApiRequest(
                operation="api",
                method="GET",
                route=base + "parts/",
                paginate=True,
            ),
        )
    )["results"]
    if request.parts is not None:
        if not set(request.parts) <= {page["pk"] for page in pages}:
            msg = "Some requested pages do not belong to the document."
            raise ValueError(msg)
        pages = [page for page in pages if page["pk"] in request.parts]
    exported = []
    for page in sorted(pages, key=lambda item: item["order"]):
        route = f"{base}parts/{page['pk']}/"
        lines = json.loads(
            execute_api(
                client,
                ApiRequest(
                    operation="api",
                    method="GET",
                    route=route + "lines/",
                    paginate=True,
                ),
            )
        )["results"]
        texts = json.loads(
            execute_api(
                client,
                ApiRequest(
                    operation="api",
                    method="GET",
                    route=route + "transcriptions/",
                    paginate=True,
                ),
            )
        )["results"]
        order = {line["pk"]: line["order"] for line in lines}
        selected = [
            text for text in texts if text["transcription"] == request.transcription_id
        ]
        selected.sort(key=lambda text: order[text["line"]])
        exported.append(
            {
                "page_id": page["pk"],
                "filename": page["filename"],
                "order": page["order"],
                "transcriptions": selected,
            }
        )
    destination = destination_path(request.destination)
    temporary = destination.with_name(destination.name + ".part")
    match request.file_format:
        case "json":
            content = json.dumps(
                {
                    "document_id": request.document_id,
                    "transcription_id": request.transcription_id,
                    "pages": exported,
                },
                ensure_ascii=False,
                indent=2,
            )
        case "text":
            content = "\n\f\n".join(
                "\n".join(text["content"] for text in page["transcriptions"])
                for page in exported
            )
        case unreachable:
            assert_never(unreachable)
    with temporary.open("x", encoding="utf-8") as output:
        _ = output.write(content)
    finish_file(temporary, destination)
    return completed_file(destination)


def download_export(client: EscriptoriumConnector, request: DownloadRequest) -> str:
    """Stream a same-origin export archive without following redirects."""
    url = same_origin(client, request.url)
    destination = destination_path(request.destination)
    temporary = destination.with_name(destination.name + ".part")
    with client.http.get(
        url, stream=True, allow_redirects=False, headers={"Accept-Encoding": "identity"}
    ) as response:
        if response.is_redirect:
            msg = "Redirected export URL refused."
            raise ValueError(msg)
        response.raise_for_status()
        with temporary.open("xb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                _ = output.write(chunk)
        expected = response.headers.get("Content-Length")
        if (
            expected
            and not response.headers.get("Content-Encoding")
            and temporary.stat().st_size != int(expected)
        ):
            msg = "Export byte count differs from Content-Length."
            raise ValueError(msg)
    finish_file(temporary, destination)
    return completed_file(destination)
