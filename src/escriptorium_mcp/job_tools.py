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
from escriptorium_mcp.model_models import ModelJob, job_label
from escriptorium_mcp.pagination import PageSelection, paginated_request
from escriptorium_mcp.task_monitoring import (
    TaskFilters,
    TaskOrdering,
    TaskState,
    read_tasks,
)
from escriptorium_mcp.training_submission import submit_training


def register_jobs(server: MCPServer) -> None:
    """Job actions enqueue work; a successful response is not task completion."""

    @server.tool(annotations=READ)
    async def list_models(
        document_id: Identifier | None = None,
        job: ModelJob | None = None,
        pagination: PageSelection | None = None,
    ) -> JsonValue:
        """List models, job type (1 segmentation, 2 recognition), and training state.

        pagination selects one native page and supports page_size up to 50;
        omitting it retains the complete legacy response.
        """
        query = {
            key: str(value)
            for key, value in (("documents", document_id), ("job", job))
            if value is not None
        }
        return await call(
            paginated_request(
                "models/", pagination, query=query, page_size_supported=True
            )
        )

    @server.tool(annotations=CREATE)
    async def upload_model(model: ModelUpload) -> JsonValue:
        """Register a local Kraken model for segmentation (1) or recognition (2)."""
        metadata = ModelMetadata(name=model.name, job=job_label(model.job))
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
    async def list_tasks(  # noqa: PLR0913 - preserve additive flat public filters
        document_id: Identifier | None = None,
        group_id: Identifier | None = None,
        ordering: TaskOrdering | None = None,
        workflow_state: TaskState | None = None,
        method: str | None = None,
        *,
        pagination: PageSelection | None = None,
    ) -> JsonValue:
        """List own reports: 0 queued, 1 running, 2 crashed, 3 done, 4 canceled.

        Document/group/order filters run on the server. State and exact method
        filters run locally after all pages when pagination is omitted. With
        pagination, local filters apply only to that native page and metadata
        reports the filtered total as source-page scoped. page_size supports up
        to 50. Ordering accepts queued_at, started_at, done_at, comma-separated
        and optionally prefixed with '-'. document_part is a display label, not
        a page ID. No arguments retains the existing response shape.
        """
        return await read_tasks(
            TaskFilters(
                document_id=document_id,
                group_id=group_id,
                ordering=ordering,
                workflow_state=workflow_state,
                method=method,
            ),
            pagination,
        )

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
        *,
        track: bool = False,
    ) -> JsonValue:
        """Queue recognition training; override replaces an owned, idle model.

        Otherwise an existing model is cloned. track=true wraps acceptance with
        candidate task groups, never a proven association or completed result.
        Monitoring failure does not undo acceptance and must not trigger a retry.
        """
        return await submit_training(document_id, job, 2, track=track)

    @server.tool(annotations=JOB)
    async def train_segmentation(
        document_id: Identifier,
        job: SegmentationTraining,
        *,
        track: bool = False,
    ) -> JsonValue:
        """Queue segmentation training from at least two distinct segmented pages.

        override=true replaces an owned, idle model; otherwise it is cloned.
        track=true reports acceptance and unproven candidate task groups.
        A monitoring failure never causes automatic resubmission.
        """
        return await submit_training(document_id, job, 1, track=track)

    @server.tool(annotations=CHANGE)
    async def cancel_task(document_id: Identifier, task_id: Identifier) -> JsonValue:
        """Cancel a report with DOCUMENT-WIDE training/import cleanup side effects.

        Even with one task ID, the server also marks all document training models
        and imports canceled. Prefer dedicated model/import cancellation for those
        jobs. Requires document owner/staff; refresh reports afterward.
        """
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
