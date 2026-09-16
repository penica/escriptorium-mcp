"""Collection training with current source and model checks before one submission."""

from typing import assert_never

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp.api import JOB, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.collection_models import CollectionMember
from escriptorium_mcp.collection_scope import (
    read_collection_items,
    require_collection_references,
)
from escriptorium_mcp.collection_training_models import (
    CollectionTraining,
    CollectionTrainingItem,
    CollectionTrainingItems,
)
from escriptorium_mcp.model_models import ModelJob, job_label
from escriptorium_mcp.training_submission import TrainingModelRecord


async def submit_collection_training(
    collection_id: Identifier, job: CollectionTraining, kind: ModelJob
) -> JsonValue:
    """Revalidate every current member without claiming the queued dataset is frozen."""
    response = TypeAdapter[list[CollectionTrainingItem] | CollectionTrainingItems](
        list[CollectionTrainingItem] | CollectionTrainingItems
    ).validate_python(await read_collection_items(collection_id))
    rows = (
        response.results if isinstance(response, CollectionTrainingItems) else response
    )
    members = [
        CollectionMember(
            document_id=row.document_id,
            page_id=row.document_part,
            transcription_id=row.transcription_layer,
        )
        for row in rows
    ]
    page_ids = {member.page_id for member in members}
    if len(page_ids) != len(members):
        msg = "The collection contains duplicate page identities."
        raise ToolError(msg)
    match kind:
        case 1:
            action, minimum_pages = "train_segmenter", 2
        case 2:
            action, minimum_pages = "train_recognizer", 1
        case _:
            assert_never(kind)
    if len(page_ids) < minimum_pages:
        msg = f"Collection training requires at least {minimum_pages} distinct pages."
        raise ToolError(msg)
    await require_collection_references(members, None)
    if job.model is not None:
        model = TrainingModelRecord.model_validate(
            await invoke("GET", f"models/{job.model}/")
        )
        if model.pk != job.model or model.job not in {kind, job_label(kind)}:
            msg = "Select the requested model with the matching training job type."
            raise ToolError(msg)
        if job.override and (model.rights != "owner" or model.training is not False):
            msg = "Overwriting requires an owned model with stopped training."
            raise ToolError(msg)
    try:
        return await invoke("POST", f"collections/{collection_id}/{action}/", job)
    except ToolError as error:
        msg = (
            f"{error} Collection training may have created a group or model, or "
            "queued a task. Inspect models and task history before retrying; "
            "no automatic retry occurred."
        )
        raise ToolError(msg) from None


def register_collection_training(server: MCPServer) -> None:
    """Expose native collection training while preserving the confirmed model ID."""

    @server.tool(annotations=JOB)
    async def train_collection_recognizer(
        collection_id: Identifier, job: CollectionTraining
    ) -> JsonValue:
        """Queue recognition training from every saved collection page/layer pair.

        The collection must be nonempty and all sources currently readable. Source
        text must supply usable ground truth; acceptance does not prove sufficiency.
        Omit model and supply model_name to create one; override=false clones a base.
        Overwrite requires an owned, stopped model even with model_name; that name
        does not rename an overwritten model. Failure can delete the target model.
        Membership is read at execution, so later edits can change the dataset.
        The native model_id identifies the target, not completion. Use model reports
        and checkpoints; collection task/group attribution is unavailable. No retry,
        per-request hyperparameters, global transcription or page subset is offered.
        """
        return await submit_collection_training(collection_id, job, 2)

    @server.tool(annotations=JOB)
    async def train_collection_segmenter(
        collection_id: Identifier, job: CollectionTraining
    ) -> JsonValue:
        """Queue segmentation training from all saved collection pages' geometry.

        Requires at least two distinct readable pages for training/validation.
        Saved layer references are checked, though segmentation uses geometry.
        Equal region/line type names across documents are combined; line offset
        comes from the first page. D-FINE fine-tuning is unsupported upstream.
        Omit model and supply model_name to create one; override=false clones a base.
        Overwrite requires an owned, stopped model regardless of model_name, which
        does not rename it. Failure can delete the target. Membership is not frozen.
        Native model_id confirms the target only; inspect model reports/checkpoints.
        No collection task/group attribution or automatic retry is available.
        """
        return await submit_collection_training(collection_id, job, 1)
