"""Automatic segmentation, OCR/HTR, training and job status."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, JOB, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.job_models import (
    CancelTask,
    ModelMetadata,
    ModelUpload,
    Recognition,
    RecognitionTraining,
    Segmentation,
    SegmentationTraining,
)


def register_jobs(server: MCPServer) -> None:
    """Job actions enqueue work; a successful response is not task completion."""

    @server.tool(annotations=READ)
    async def list_models() -> JsonValue:
        """List models, job type (1 segmentation, 2 recognition), and training state."""
        return await call(ApiRequest(method="GET", route="models/", paginate=True))

    @server.tool(annotations=CREATE)
    async def upload_model(model: ModelUpload) -> JsonValue:
        """Register a local Kraken model for segmentation (1) or recognition (2)."""
        metadata = ModelMetadata(name=model.name, job=model.job)
        return await call(
            ApiRequest(
                method="POST",
                route="models/",
                file_path=model.file_path,
                file_field="file",
                body_json=metadata.model_dump_json(),
            ),
            timeout_seconds=1800,
        )

    @server.tool(annotations=READ)
    async def get_model(model_id: Identifier) -> JsonValue:
        """Read model training progress, versions and available accuracy metadata."""
        return await invoke("GET", f"models/{model_id}/")

    @server.tool(annotations=READ)
    async def list_tasks() -> JsonValue:
        """List task reports: 0 queued, 1 running, 2 crashed, 3 done, 4 canceled."""
        return await call(ApiRequest(method="GET", route="tasks/", paginate=True))

    @server.tool(annotations=READ)
    async def get_task(task_id: Identifier) -> JsonValue:
        """Read a task report's status, messages and timestamps."""
        return await invoke("GET", f"tasks/{task_id}/")

    @server.tool(annotations=JOB)
    async def segment_pages(document_id: Identifier, job: Segmentation) -> JsonValue:
        """Queue automatic segmentation; override replaces existing geometry."""
        return await invoke("POST", f"documents/{document_id}/segment/", job)

    @server.tool(annotations=JOB)
    async def transcribe_pages(document_id: Identifier, job: Recognition) -> JsonValue:
        """Queue OCR/HTR; existing text in the selected layer may be replaced."""
        return await invoke("POST", f"documents/{document_id}/transcribe/", job)

    @server.tool(annotations=JOB)
    async def train_recognition(
        document_id: Identifier,
        job: RecognitionTraining,
    ) -> JsonValue:
        """Queue recognition model training from selected ground-truth pages."""
        return await invoke("POST", f"documents/{document_id}/train/", job)

    @server.tool(annotations=JOB)
    async def train_segmentation(
        document_id: Identifier,
        job: SegmentationTraining,
    ) -> JsonValue:
        """Queue segmentation training from at least two segmented pages."""
        return await invoke("POST", f"documents/{document_id}/segtrain/", job)

    @server.tool(annotations=CHANGE)
    async def cancel_task(document_id: Identifier, task_id: Identifier) -> JsonValue:
        """Cancel a queued/running task using the server's cancellation action."""
        return await invoke(
            "POST",
            f"documents/{document_id}/cancel_tasks/",
            CancelTask(task_report=task_id),
        )

    @server.tool(annotations=CHANGE)
    async def cancel_page_tasks(
        document_id: Identifier, page_id: Identifier
    ) -> JsonValue:
        """Cancel pending processing for one page."""
        return await invoke("POST", f"documents/{document_id}/parts/{page_id}/cancel/")

    @server.tool(annotations=CHANGE)
    async def cancel_model_training(model_id: Identifier) -> JsonValue:
        """Stop training an existing model using the dedicated cancel action."""
        return await invoke("POST", f"models/{model_id}/cancel_training/")
