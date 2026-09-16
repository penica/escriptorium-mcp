"""Source checks retain the different layer semantics of both alignment actions."""

from typing import Annotated, assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, TypeAdapter

from escriptorium_mcp.alignment_models import (
    AlignmentJob,
    BeamSearch,
    ExistingWitness,
    ForcedAlignmentJob,
    NativeAlignment,
    OffsetSearch,
    UploadedWitness,
)
from escriptorium_mcp.api import ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.job_models import Parts
from escriptorium_mcp.model_models import JobLabel, ModelJob, ModelRecord
from escriptorium_mcp.text_scope import RecordId, RecordPage
from escriptorium_mcp.witness_scope import read_witness, validate_witness_file


class AlignmentDocument(RecordId):
    """The selected document's enabled region types constrain matching input."""

    valid_block_types: list[RecordId] = Field(default_factory=list)


class AlignmentLayer(RecordId):
    """Ordinary alignment needs an active source and its actual name for comparison."""

    name: str
    archived: Annotated[bool, Field(strict=True)]


class ForcedAlignmentModel(ModelRecord):
    """Readable model metadata cannot prove the weights support forced alignment."""

    job: ModelJob | JobLabel | None = None


async def require_alignment_parts(document_id: Identifier, parts: Parts | None) -> None:
    """Check every selected page against the complete scoped page collection."""
    if parts is None:
        return
    response = await call(
        ApiRequest(
            method="GET",
            route=f"documents/{document_id}/parts/",
            paginate=True,
            strict_pagination=True,
        )
    )
    parsed = TypeAdapter[list[RecordId] | RecordPage](
        list[RecordId] | RecordPage
    ).validate_python(response)
    rows = (
        [RecordId.model_validate(row) for row in parsed.results]
        if isinstance(parsed, RecordPage)
        else parsed
    )
    if not set(parts).issubset({row.pk for row in rows}):
        msg = "An alignment page is outside the requested document."
        raise ToolError(msg)


async def prepare_alignment(document_id: Identifier, job: AlignmentJob) -> ApiRequest:
    """Build one scoped native request with acknowledged target-name reuse."""
    document = AlignmentDocument.model_validate(
        await invoke("GET", f"documents/{document_id}/")
    )
    if document.pk != document_id:
        msg = "The server returned a different alignment document."
        raise ToolError(msg)
    source = AlignmentLayer.model_validate(
        await invoke(
            "GET", f"documents/{document_id}/transcriptions/{job.transcription}/"
        )
    )
    if source.pk != job.transcription or source.archived:
        msg = "Ordinary alignment requires an active source in the requested document."
        raise ToolError(msg)
    if job.layer_name == source.name:
        msg = "The alignment target cannot reuse the source transcription's name."
        raise ToolError(msg)
    await require_alignment_parts(document_id, job.parts)
    enabled = [str(row.pk) for row in document.valid_block_types] + [
        "Undefined",
        "Orphan",
    ]
    regions = (
        [str(value) for value in job.region_types]
        if job.region_types is not None
        else enabled
    )
    if not set(regions).issubset(enabled):
        msg = "An alignment region type is not enabled for the requested document."
        raise ToolError(msg)
    file_path = None
    witness_id = None
    match job.witness:
        case ExistingWitness(witness_id=identifier):
            _ = await read_witness(identifier)
            witness_id = identifier
        case UploadedWitness(file_path=path):
            await validate_witness_file(path, standalone=False)
            file_path = path
        case _:
            assert_never(job.witness)
    match job.search:
        case BeamSearch(beam_size=beam):
            beam_size, max_offset = beam, 0
        case OffsetSearch(max_offset=offset):
            beam_size, max_offset = 0, offset
        case _:
            assert_never(job.search)
    body = NativeAlignment(
        transcription=job.transcription,
        existing_witness=witness_id,
        parts=job.parts,
        layer_name=job.layer_name,
        region_types=regions,
        n_gram=job.n_gram,
        gap=job.gap,
        threshold=job.threshold,
        merge=job.merge,
        add_hyphens=job.add_hyphens,
        full_doc=job.full_doc,
        beam_size=beam_size,
        max_offset=max_offset,
    )
    return ApiRequest(
        method="POST",
        route=f"documents/{document_id}/align/",
        body_json=body.model_dump_json(exclude_none=True),
        file_path=file_path,
        file_field="witness_file",
        single_attempt=True,
    )


async def prepare_forced_alignment(
    document_id: Identifier, job: ForcedAlignmentJob
) -> ApiRequest:
    """Let the native action validate its layer, including archived layers."""
    document = RecordId.model_validate(await invoke("GET", f"documents/{document_id}/"))
    if document.pk != document_id:
        msg = "The server returned a different forced-alignment document."
        raise ToolError(msg)
    await require_alignment_parts(document_id, job.parts)
    model = ForcedAlignmentModel.model_validate(
        await invoke("GET", f"models/{job.model}/")
    )
    if model.pk != job.model or model.job not in {None, 2, "Recognize"}:
        msg = "Select the requested readable recognition model for forced alignment."
        raise ToolError(msg)
    return ApiRequest(
        method="POST",
        route=f"documents/{document_id}/forced_align/",
        body_json=job.model_dump_json(exclude_none=True),
        single_attempt=True,
    )
