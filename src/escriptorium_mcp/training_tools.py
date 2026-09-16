"""Read model validation metrics alongside explicitly selected training reports."""

from typing import assert_never

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import READ, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.task_monitoring import TaskFilters, job_status
from escriptorium_mcp.training_submission import TrainingModelRecord


def register_training(server: MCPServer) -> None:
    """Keep validation metrics distinct from independent evaluation and success."""

    @server.tool(annotations=READ)
    async def get_training_report(
        model_id: Identifier,
        document_id: Identifier | None = None,
        group_id: Identifier | None = None,
    ) -> JsonValue:
        """Read model metrics/checkpoints and optionally selected training tasks.

        A supplied document/group is caller-selected, not a proven model link.
        Without a group, document task reports include historical training.
        Idle models are not proof of successful training. Server validation
        scores are not universal CER/WER metrics. Artifact existence is unchecked;
        use download_model to verify a current file or checkpoint's availability.
        """
        if group_id is not None and document_id is None:
            message = "A task group requires its document_id."
            raise ToolError(message)
        model = TrainingModelRecord.model_validate(
            await invoke("GET", f"models/{model_id}/")
        )
        match model.job:
            case 1 | "Segment":
                method = "core.tasks.segtrain"
            case 2 | "Recognize":
                method = "core.tasks.train"
            case _:
                assert_never(model.job)
        task_status = (
            await job_status(
                TaskFilters(document_id=document_id, group_id=group_id, method=method)
            )
            if document_id is not None
            else None
        )
        return {
            "model_id": model_id,
            "name": model.name,
            "job": model.job,
            "training": model.training,
            "accuracy_percent": model.accuracy_percent,
            "current_file": model.file,
            "checkpoints": [version.as_json() for version in model.versions],
            "artifact_availability": "not_checked",
            "task_status": task_status,
            "task_model_link": (
                "caller_supplied" if document_id is not None else "not_requested"
            ),
            "limitations": (
                "Model state, task history and file references are separate "
                "observations, not an atomic result. Idle is not success; a "
                "caller-selected group is not proven to train this model. "
                "Validation-score meaning depends on model/server; no independent "
                "evaluation or CER/WER is calculated. Missing/zero metrics remain "
                "unchanged. Advertised historical checkpoints can be removed."
            ),
        }
