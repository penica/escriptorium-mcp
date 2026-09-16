"""Typed private requests for additional eScriptorium REST endpoints."""

from typing import ClassVar, Final, Literal

from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, FilePath, JsonValue

from escriptorium_mcp.bridge import call

READ: Final = ToolAnnotations(read_only_hint=True, destructive_hint=False)
CREATE: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False
)
CHANGE: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True
)
JOB: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False
)
DELETE: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True
)


class Input(BaseModel):
    """Reject misspelled fields before a request reaches eScriptorium."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class ApiRequest(Input):
    """Internal request; callers cannot choose arbitrary URLs through MCP."""

    operation: Literal["api"] = "api"
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    route: str
    body_json: str = "{}"
    file_path: FilePath | None = None
    file_field: Literal["image", "file", "upload_file", "witness_file"] = "image"
    paginate: bool = False
    strict_pagination: Literal[True] | None = None
    single_attempt: Literal[True] | None = None
    query: dict[str, str] = Field(default_factory=dict)


async def invoke(
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    route: str,
    body: BaseModel | None = None,
) -> JsonValue:
    """Serialize validated domain fields while preserving explicit nulls."""
    return await call(
        ApiRequest(
            method=method,
            route=route,
            body_json=body.model_dump_json(exclude_unset=True) if body else "{}",
        )
    )
