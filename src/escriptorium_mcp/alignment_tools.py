"""Reference-text alignment and in-place character-graph alignment are distinct jobs."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.alignment_models import AlignmentJob, ForcedAlignmentJob
from escriptorium_mcp.alignment_scope import prepare_forced_alignment
from escriptorium_mcp.alignment_submission import send_alignment, submit_alignment
from escriptorium_mcp.api import JOB
from escriptorium_mcp.bridge import Identifier


def register_alignment(server: MCPServer) -> None:
    """Register two native actions without inventing completion or cancellation APIs."""

    @server.tool(annotations=JOB)
    async def align_document(
        document_id: Identifier, job: AlignmentJob, *, track: bool = False
    ) -> JsonValue:
        """Align an active transcription to owned reference text or a local UTF-8 TXT.

        Required acknowledge_target_reuse=true accepts that layer_name can reuse
        and modify existing text, including hidden archived targets. The source
        layer's name is always rejected after trimming. Target absence cannot be
        guaranteed. A direct file upload creates an owned witness while queuing.
        Omit parts/types for all. merge=false leaves old unmatched target text;
        merge=true can copy source text outside selected regions. full_doc=true
        reads all source pages even when output parts select only some pages.
        Beam and offset search explicitly disable each other; offset zero is valid.
        Success is native acceptance, not completed or quality-checked output.
        Optional tracking returns unconfirmed group candidates and survives read
        failures. Use task reports with method core.tasks.align. Native Passim
        availability, rollback and precise alignment cancellation are not assured.
        """
        return await submit_alignment(document_id, job, track=track)

    @server.tool(annotations=JOB)
    async def force_align_pages(
        document_id: Identifier, job: ForcedAlignmentJob
    ) -> JsonValue:
        """Replace character positions/confidences in an existing transcription layer.

        Uses a readable recognition model and existing text/geometry; it does not
        rewrite text, geometry or create a layer. Native document-scoped validation
        permits archived layers, so no active-only layer lookup is imposed here.
        Model metadata does not prove binary compatibility. Omit parts for all pages.
        One request queues page jobs without a group; failures may leave some jobs
        queued or graphs changed. No MCP retry occurs, but the backend may retry.
        Inspect core.tasks.forced_align reports; acceptance is not completion or
        proof of model attribution. No automatic graph backup or rollback exists.
        """
        return await send_alignment(await prepare_forced_alignment(document_id, job))
