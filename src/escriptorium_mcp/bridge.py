"""Bounded subprocess transport to the legacy connector."""

import shutil
from typing import Annotated, ClassVar, Literal

import anyio
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
)

from escriptorium_mcp.settings import load_settings, worker_environment

Identifier = Annotated[int, Field(gt=0, strict=True)]
Name = Annotated[str, Field(min_length=1, max_length=255, pattern=r"\S")]
Operation = Literal[
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
    """Validated operation passed to the private worker."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    operation: Operation
    document_id: Identifier | None = None
    page_id: Identifier | None = None
    project_id: Identifier | None = None
    name: Name | None = None


class WorkerFailure(BaseModel):
    """Sanitized error metadata, never an upstream response body."""

    error_type: str
    http_status: int | None = None


async def call(request: BaseModel, *, timeout_seconds: float = 120) -> JsonValue:
    """Execute off-process with a hard deadline and sanitized failures."""
    settings = load_settings()
    if settings.url is None or not (
        settings.api_key.get_secret_value()
        or (settings.username and settings.password.get_secret_value())
    ):
        msg = (
            "Set ESCRIPTORIUM_URL and API_KEY, or USERNAME and PASSWORD (same prefix)."
        )
        raise ToolError(msg)
    uv = shutil.which("uv")
    if uv is None:
        msg = "Install uv and sync the worker environment before using this server."
        raise ToolError(msg)
    environment = worker_environment(settings)
    try:
        with anyio.fail_after(timeout_seconds):
            result = await anyio.run_process(
                [
                    uv,
                    "run",
                    "--frozen",
                    "--project",
                    str(settings.worker_dir),
                    "python",
                    str(settings.worker_dir / "bridge.py"),
                ],
                input=request.model_dump_json(exclude_none=True).encode(),
                env=environment,
                check=False,
            )
    except TimeoutError:
        msg = (
            "Connector timed out. A write may have completed; inspect before retrying."
        )
        raise ToolError(msg) from None
    if result.returncode:
        try:
            failure = WorkerFailure.model_validate_json(result.stdout)
        except ValidationError:
            msg = "Worker failed to start. Check the worker installation and uv sync."
            raise ToolError(msg) from None
        messages = {
            "FileExistsError": "Destination exists; choose a new path.",
            "FileNotFoundError": "Source file or destination mount is unavailable.",
            "PermissionError": "File or NAS permissions prevent this operation.",
            "ArchiveError": "Acquisition stopped; check NAS and partial manifest.",
            "PageOrderLookupError": (
                "Page lookup did not return a page; check the document "
                "and zero-based page order."
            ),
        }
        msg = messages.get(
            failure.error_type,
            "Connector failed; check inputs and server compatibility.",
        )
        if failure.http_status is not None:
            msg = f"eScriptorium HTTP {failure.http_status}; check inputs/access."
        raise ToolError(msg)
    return TypeAdapter[JsonValue](JsonValue).validate_json(result.stdout)
