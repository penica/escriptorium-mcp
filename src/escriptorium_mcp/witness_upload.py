"""One standalone upload with honest, bounded ownership-readback diagnostics."""

import json
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.witness_models import (
    OwnershipReadback,
    WitnessIdentity,
    WitnessRecord,
    WitnessUpload,
)
from escriptorium_mcp.witness_scope import validate_witness_file


def _diagnose(
    witness_id: Identifier, submission: JsonValue, record: JsonValue
) -> OwnershipReadback:
    """Classify metadata contradictions without hiding either native response."""
    reason: Literal["missing_owner", "owner_mismatch"] | None = None
    try:
        detail = WitnessRecord.model_validate(record)
    except ValidationError:
        return OwnershipReadback(
            status="unverified",
            reason="invalid_readback_metadata",
            witness_id=witness_id,
            record=record,
        )
    if detail.pk != witness_id:
        return OwnershipReadback(
            status="unverified",
            reason="identity_mismatch",
            witness_id=witness_id,
            record=record,
        )
    try:
        created = WitnessRecord.model_validate(submission)
    except ValidationError:
        return OwnershipReadback(
            status="unverified",
            reason="invalid_create_metadata",
            witness_id=witness_id,
            record=record,
        )
    if (
        not created.owner
        or not created.owner.strip()
        or not detail.owner
        or not detail.owner.strip()
    ):
        reason = "missing_owner"
    elif created.owner != detail.owner:
        reason = "owner_mismatch"
    return OwnershipReadback(
        status="verified" if reason is None else "unverified",
        reason=reason,
        witness_id=witness_id,
        record=record,
    )


async def _readback(submission: JsonValue) -> OwnershipReadback:
    """Attempt at most one owned GET using only a validated successful-create pk."""
    try:
        witness_id = WitnessIdentity.model_validate(submission).pk
    except ValidationError:
        return OwnershipReadback(
            status="unavailable", reason="missing_identity", witness_id=None
        )
    try:
        record = await call(
            ApiRequest(
                method="GET",
                route=f"textual-witnesses/{witness_id}/",
                single_attempt=True,
            )
        )
    except ToolError as error:
        return OwnershipReadback(
            status="unavailable",
            reason="readback_failed",
            witness_id=witness_id,
            error=str(error),
        )
    except ValidationError:
        return OwnershipReadback(
            status="unavailable",
            reason="readback_failed",
            witness_id=witness_id,
            error="The owned witness readback did not return valid JSON metadata.",
        )
    except OSError:
        return OwnershipReadback(
            status="unavailable",
            reason="readback_failed",
            witness_id=witness_id,
            error="The local worker could not complete the owned witness readback.",
        )
    return _diagnose(witness_id, submission, record)


async def submit_witness(upload: WitnessUpload) -> JsonValue:
    """Retain native acceptance even when ownership cannot be verified afterward."""
    await validate_witness_file(upload.file_path, standalone=True)
    try:
        submission = await call(
            ApiRequest(
                method="POST",
                route="textual-witnesses/",
                body_json=json.dumps({"name": upload.name}),
                file_path=upload.file_path,
                file_field="file",
                single_attempt=True,
            ),
            timeout_seconds=1800,
        )
    except ToolError as error:
        msg = (
            f"{error} A textual witness may already exist and may be inaccessible. "
            "Inspect native records before retrying; no automatic retry occurred."
        )
        raise ToolError(msg) from None
    readback = await _readback(submission)
    return {
        "accepted": True,
        "submission": submission,
        "ownership_readback": TypeAdapter[JsonValue](JsonValue).validate_json(
            readback.model_dump_json()
        ),
        "limitations": (
            "Acceptance is not proof of usable ownership. Some native versions "
            "create ownerless witnesses. Readback describes current owned-route "
            "visibility only; no ownership repair, cleanup or retry was attempted."
        ),
    }
