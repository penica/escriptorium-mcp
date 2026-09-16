"""Training guards and best-effort task-group attribution after one submission."""

from typing import assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.job_models import Training
from escriptorium_mcp.model_models import JobLabel, ModelJob, ModelRecord, job_label
from escriptorium_mcp.submission_tracking import (
    SubmissionGroup,
    read_submission_groups,
)


class TrainingModelRecord(ModelRecord):
    """Parse model kind and optional metrics without treating idle as successful."""

    job: ModelJob | JobLabel
    name: str | None = None
    accuracy_percent: float | None = None


async def submit_training(
    document_id: Identifier, job: Training, kind: ModelJob, *, track: bool
) -> JsonValue:
    """Submit once; preserve acceptance even if optional follow-up reads fail."""
    if job.model is not None:
        model = TrainingModelRecord.model_validate(
            await invoke("GET", f"models/{job.model}/")
        )
        if model.job not in {kind, job_label(kind)}:
            message = "Select a model whose job matches this training action."
            raise ToolError(message)
        if job.override and (model.rights != "owner" or model.training is not False):
            message = "Overwriting requires an owned model with stopped training."
            raise ToolError(message)
    before = await read_submission_groups(document_id) if track else None
    match kind:
        case 1:
            action = "segtrain"
        case 2:
            action = "train"
        case _:
            assert_never(kind)
    submission = await invoke("POST", f"documents/{document_id}/{action}/", job)
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
            and group.method in {None, f"core.tasks.{action}"}
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
                "Document training returns no group/model ID. New groups are only "
                "candidates, including a single match. Concurrent submissions, "
                "delayed reports and failed reads prevent reliable attribution. "
                "Acceptance is not completion. Do not resubmit to fix monitoring."
            ),
        },
    }
