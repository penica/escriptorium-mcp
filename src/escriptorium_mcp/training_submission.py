"""Training guards and best-effort task-group attribution after one submission."""

from typing import ClassVar, assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.job_models import Training
from escriptorium_mcp.model_models import JobLabel, ModelJob, ModelRecord, job_label


class TrainingModelRecord(ModelRecord):
    """Parse model kind and optional metrics without treating idle as successful."""

    job: ModelJob | JobLabel
    name: str | None = None
    accuracy_percent: float | None = None


class TrainingGroup(BaseModel):
    """Keep unknown group fields; a missing method cannot establish attribution."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    pk: Identifier
    method: str | None = None

    def as_json(self) -> JsonValue:
        """Retain the server's group fields without adding absent optional fields."""
        return TypeAdapter[JsonValue](JsonValue).validate_json(
            self.model_dump_json(exclude_unset=True)
        )


class TrainingGroupPage(BaseModel):
    """Parse the paginated response after the adapter has followed next links."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    results: list[TrainingGroup]


async def read_training_groups(document_id: Identifier) -> list[TrainingGroup] | None:
    """Keep optional monitoring failures from turning accepted writes into retries."""
    try:
        raw = await call(
            ApiRequest(
                method="GET",
                route=f"documents/{document_id}/task_groups/",
                paginate=True,
            )
        )
        parsed = TypeAdapter[list[TrainingGroup] | TrainingGroupPage](
            list[TrainingGroup] | TrainingGroupPage
        ).validate_python(raw)
    except (ToolError, ValidationError):
        return None
    match parsed:
        case TrainingGroupPage(results=groups):
            return groups
        case list():
            return parsed
        case _:
            assert_never(parsed)


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
    before = await read_training_groups(document_id) if track else None
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
    after = await read_training_groups(document_id)
    candidates: list[TrainingGroup] = []
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
