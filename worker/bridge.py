"""Run one connector operation in its Pydantic 1 environment."""

import json
import os
import sys
from contextlib import redirect_stdout
from typing import Literal, assert_never

from archive import ArchiveRequest, download_register
from escriptorium_connector import EscriptoriumConnector
from escriptorium_connector.connector_errors import (
    EscriptoriumConnectorError,
    EscriptoriumConnectorHttpError,
)
from escriptorium_connector.dtos import PostAbbreviatedTranscription, PostProject
from exports import (
    DownloadRequest,
    ExportRequest,
    download_export,
    export_transcriptions,
)
from ontology_native import NativeRequest, execute_native
from pages import PagesByOrderRequest, read_page_by_order, read_pages, read_regions
from pydantic import BaseModel, ValidationError
from pydantic.json import pydantic_encoder
from requests.exceptions import RequestException
from rest import ApiRequest, execute_api

LegacyOperation = Literal[
    "list_projects",
    "get_project",
    "list_documents",
    "get_document",
    "list_pages",
    "get_page",
    "list_lines",
    "list_regions",
    "list_transcriptions",
    "get_page_transcriptions",
    "create_project",
    "create_transcription",
]


class Request(BaseModel):
    """Private wire request emitted by the MCP adapter."""

    operation: LegacyOperation
    document_id: int = 0
    page_id: int = 0
    project_id: int = 0
    name: str = ""

    class Config:
        """Reject unsupported private wire fields."""

        frozen = True
        extra = "forbid"


def execute(client: EscriptoriumConnector, request: Request) -> str:
    """Dispatch only explicitly supported connector operations."""
    match request.operation:
        case "list_projects":
            result = client.get_projects()
        case "get_project":
            result = client.get_project(request.project_id)
        case "list_documents":
            result = client.get_documents()
        case "get_document":
            result = client.get_document(request.document_id)
        case "list_pages":
            return read_pages(client, request.document_id, 0)
        case "get_page":
            return read_pages(client, request.document_id, request.page_id)
        case "list_lines":
            result = client.get_document_part_lines(
                request.document_id, request.page_id
            )
        case "list_regions":
            return read_regions(client, request.document_id, request.page_id)
        case "list_transcriptions":
            result = client.get_document_transcriptions(request.document_id)
        case "get_page_transcriptions":
            result = client.get_document_part_transcriptions(
                request.document_id,
                request.page_id,
            )
        case "create_project":
            result = client.create_project(PostProject(name=request.name))
        case "create_transcription":
            result = client.create_document_transcription(
                request.document_id,
                PostAbbreviatedTranscription(name=request.name),
            )
        case unreachable:
            assert_never(unreachable)
    return json.dumps(result, default=pydantic_encoder, ensure_ascii=False)


class Envelope(BaseModel):
    """Select the private request parser without executing arbitrary methods."""

    operation: (
        LegacyOperation
        | Literal[
            "api",
            "download_register",
            "export_transcriptions",
            "download_export",
            "ontology_native",
            "page_by_order",
        ]
    )


def dispatch(client: EscriptoriumConnector, raw: str) -> str:
    """Parse a request using its operation-specific model."""
    match Envelope.parse_raw(raw).operation:
        case "page_by_order":
            result = read_page_by_order(client, PagesByOrderRequest.parse_raw(raw))
        case "ontology_native":
            result = execute_native(client, NativeRequest.parse_raw(raw))
        case "api":
            result = execute_api(client, ApiRequest.parse_raw(raw))
        case "download_register":
            result = download_register(client, ArchiveRequest.parse_raw(raw))
        case "export_transcriptions":
            result = export_transcriptions(client, ExportRequest.parse_raw(raw))
        case "download_export":
            result = download_export(client, DownloadRequest.parse_raw(raw))
        case (
            "list_projects"
            | "get_project"
            | "list_documents"
            | "get_document"
            | "list_pages"
            | "get_page"
            | "list_lines"
            | "list_regions"
            | "list_transcriptions"
            | "get_page_transcriptions"
            | "create_project"
            | "create_transcription"
        ):
            result = execute(client, Request.parse_raw(raw))
        case unreachable:
            assert_never(unreachable)
    return result


def main() -> None:
    """Keep stdout exclusively for JSON; sanitize upstream error messages."""
    try:
        raw = sys.stdin.read()
        with redirect_stdout(sys.stderr):
            client = EscriptoriumConnector(
                base_url=os.environ["ESCRIPTORIUM_URL"],
                api_key=os.environ.get("ESCRIPTORIUM_API_KEY") or None,
                username=os.environ.get("ESCRIPTORIUM_USERNAME") or None,
                password=os.environ.get("ESCRIPTORIUM_PASSWORD") or None,
                http_read_timeout=30,
            )
            for adapter in client.http.adapters.values():
                adapter.max_retries = adapter.max_retries.new(
                    allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"})
                )
            with client.http:
                result = dispatch(client, raw)
        sys.stdout.write(result)
    except EscriptoriumConnectorHttpError as error:
        sys.stdout.write(
            json.dumps(
                {
                    "error_type": type(error).__name__,
                    "http_status": error.error.response.status_code,
                }
            )
        )
        sys.exit(1)
    except (
        EscriptoriumConnectorError,
        RequestException,
        ValidationError,
        KeyError,
        IndexError,
        ValueError,
        TypeError,
        OSError,
    ) as error:
        # Upstream errors may contain credentials or full private response bodies.
        sys.stdout.write(json.dumps({"error_type": type(error).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
