"""Single alignment submissions and optional unconfirmed group candidates."""

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.alignment_models import AlignmentJob
from escriptorium_mcp.alignment_scope import prepare_alignment
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.submission_tracking import SubmissionGroup, read_submission_groups


async def send_alignment(request: ApiRequest) -> JsonValue:
    """Retain partial job/witness/write uncertainty without resubmitting the request."""
    try:
        return await call(request, timeout_seconds=1800)
    except ToolError as error:
        msg = (
            f"{error} Alignment page jobs may already be queued. Ordinary alignment "
            "may also have created a witness/group. Text or character graphs may "
            "change partially; inspect task reports before retrying. "
            "No automatic MCP retry occurred."
        )
        raise ToolError(msg) from None


async def submit_alignment(
    document_id: Identifier, job: AlignmentJob, *, track: bool
) -> JsonValue:
    """Preserve accepted submission even if optional group monitoring is unavailable."""
    request = await prepare_alignment(document_id, job)
    before = await read_submission_groups(document_id) if track else None
    submission = await send_alignment(request)
    if not track:
        return submission
    after = await read_submission_groups(document_id)
    candidates: list[SubmissionGroup] = []
    status = "unavailable"
    if before is not None and after is not None:
        previous_ids = {group.pk for group in before}
        candidates = [
            group
            for group in after
            if group.pk not in previous_ids
            and group.method in {None, "core.tasks.align"}
        ]
        status = "none"
        if candidates:
            status = "candidate" if len(candidates) == 1 else "ambiguous"
    return {
        "accepted": True,
        "submission": submission,
        "tracking": {
            "status": status,
            "candidates": [group.as_json() for group in candidates],
            "attribution_confirmed": False,
            "limitations": (
                "Alignment returns no witness/task/group/output-layer ID. New groups "
                "are unconfirmed candidates, including a single match. Concurrent "
                "submissions, delayed reports and failed reads prevent reliable "
                "attribution. Acceptance is not completion; do not resubmit to "
                "fix monitoring."
            ),
        },
    }
