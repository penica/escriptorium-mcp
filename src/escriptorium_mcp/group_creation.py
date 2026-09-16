"""One native creation with bounded, acceptance-preserving rights observation."""

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.account_scope import read_current_user
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.group_models import (
    GroupName,
    GroupNameBody,
    GroupReadback,
    GroupVerification,
)
from escriptorium_mcp.text_scope import RecordId


def inspect_group_readback(
    record: JsonValue, group_id: Identifier, creator_id: Identifier
) -> GroupVerification:
    """Only matching detail identity and explicit rights can verify usable creation."""
    try:
        detail = GroupReadback.model_validate(record)
    except ValidationError:
        return GroupVerification()
    if detail.pk != group_id:
        return GroupVerification()
    member = (
        any(user.pk == creator_id for user in detail.users)
        if "users" in detail.model_fields_set
        else None
    )
    owner = detail.owner == creator_id if "owner" in detail.model_fields_set else None
    return GroupVerification(
        status="verified" if member is True and owner is True else "incomplete",
        readable=True,
        creator_is_member=member,
        creator_is_owner=owner,
        readback=record,
    )


async def verify_group_creation(
    submission: JsonValue, creator_id: Identifier
) -> GroupVerification:
    """Read at most once without turning failed verification into failed creation."""
    try:
        group_id = RecordId.model_validate(submission).pk
    except ValidationError:
        return GroupVerification()
    try:
        record = await call(
            ApiRequest(method="GET", route=f"groups/{group_id}/", single_attempt=True)
        )
    except (ToolError, ValidationError, OSError):
        return GroupVerification()
    return inspect_group_readback(record, group_id, creator_id)


async def submit_group(name: GroupName) -> JsonValue:
    """Preserve native acceptance even when the new group is inaccessible afterward."""
    creator = RecordId.model_validate(await read_current_user())
    try:
        submission = await call(
            ApiRequest(
                method="POST",
                route="groups/",
                body_json=GroupNameBody(name=name).model_dump_json(),
                single_attempt=True,
            )
        )
    except ToolError as error:
        msg = (
            f"{error} A group may already exist without creator membership or "
            "ownership. Inspect native records before retrying; no automatic "
            "repair, retry or cleanup occurred."
        )
        raise ToolError(msg) from None
    verification = await verify_group_creation(submission, creator.pk)
    return {
        "accepted": True,
        "submission": submission,
        "verification": TypeAdapter[JsonValue](JsonValue).validate_json(
            verification.model_dump_json()
        ),
    }
