"""Native font identity and action-specific writable-field capability checks."""

from typing import ClassVar, Literal, assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    ValidationError,
)

from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.text_scope import RecordId


class FontOptions(BaseModel):
    """Read native action fields without assuming unrelated serializer details."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    actions: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)


class FontField(BaseModel):
    """Require an explicit boolean permission instead of a guessed default."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    read_only: StrictBool


async def read_font(font_id: Identifier) -> JsonValue:
    """Verify catalogue identity and preserve all native font metrics and URLs."""
    raw = await invoke("GET", f"fonts/{font_id}/")
    if RecordId.model_validate(raw).pk != font_id:
        msg = "The server returned a different font; no writes were sent."
        raise ToolError(msg)
    return raw


async def require_font_assignment(
    route: str, method: Literal["POST", "PATCH"], font_id: Identifier | None
) -> None:
    """Check the correct record action before assigning or clearing a font."""
    raw = await invoke("OPTIONS", route)
    try:
        options = FontOptions.model_validate(raw)
        match method:
            case "POST":
                fields = options.actions.get("POST", {})
            case "PATCH":
                fields = options.actions.get("PATCH", options.actions.get("PUT", {}))
            case _:
                assert_never(method)
        field = FontField.model_validate(fields.get("transcription_font"))
    except ValidationError:
        msg = "Server metadata does not confirm writable transcription_font here."
        raise ToolError(msg) from None
    if field.read_only:
        msg = "The server marks transcription_font read-only for this operation."
        raise ToolError(msg)
    if font_id is not None:
        _ = await read_font(font_id)


async def save_record(
    method: Literal["POST", "PATCH"],
    route: str,
    body: BaseModel,
    font_id: Identifier | None,
) -> JsonValue:
    """Guard supplied font changes; leave omitted-font request behavior intact."""
    supplied = "transcription_font" in body.model_fields_set
    if supplied:
        await require_font_assignment(route, method, font_id)
    return await call(
        ApiRequest(
            method=method,
            route=route,
            body_json=body.model_dump_json(exclude_unset=True),
            single_attempt=True if supplied else None,
        )
    )
