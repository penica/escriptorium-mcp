"""Native group names and explicit observations of creator membership/ownership."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, JsonValue, StrictBool, StrictStr

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.text_scope import RecordId

GroupName = Annotated[StrictStr, Field(min_length=1, max_length=150, pattern=r"\S")]


def require_native_create_acknowledgment(value: StrictBool) -> bool:
    """Require exact JSON true for known native membership/ownership limitations."""
    if not value:
        msg = "Acknowledge native group creation limitations with true."
        raise ValueError(msg)
    return value


NativeCreateAcknowledgment = Annotated[
    StrictBool,
    AfterValidator(require_native_create_acknowledgment),
    Field(json_schema_extra={"const": True}),
]


class GroupNameBody(Input):
    """Name is the only writable native field; acknowledgments stay local."""

    name: GroupName


class GroupReadback(RecordId):
    """Field presence distinguishes unknown evidence from observed nonmembership."""

    users: list[RecordId] = Field(default_factory=list)
    owner: Identifier | None = None


class GroupVerification(Input):
    """Creation acceptance is separate from observed access and creator rights."""

    status: Literal["verified", "incomplete", "unavailable"] = "unavailable"
    readable: bool | None = None
    creator_is_member: bool | None = None
    creator_is_owner: bool | None = None
    readback: JsonValue = None
    limitations: str = (
        "Native creation may omit creator membership and ownership. These are "
        "current readback observations only. "
        "No repair, retry or rollback was attempted."
    )
