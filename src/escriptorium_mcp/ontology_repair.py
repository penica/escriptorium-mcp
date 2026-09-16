"""Previewable document-scoped type reassignment and merges."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.api import CHANGE, READ, Input, invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.ontology_models import ContentKind, TypeReplacement
from escriptorium_mcp.ontology_scan import Element, audit, inventory
from escriptorium_mcp.ontology_tools import read_ontology, selection


class AssignmentPatch(Input):
    """Send only the type field; preserve geometry, text and metadata."""

    typology: int | None


async def replace(document_id: int, change: TypeReplacement) -> JsonValue:
    """Stop on errors/conflicts and return progress instead of hiding partial writes."""
    ontology = await read_ontology(document_id)
    allowed = {item.pk for item in ontology.types(change.kind)}
    if change.target_type_id is not None and change.target_type_id not in allowed:
        msg = "Enable the target type in this document and use its resulting ID first."
        raise ToolError(msg)
    matches = [
        row
        for row in await inventory(document_id, change.kind)
        if row.type_id == change.source_type_id
    ]
    result: dict[str, JsonValue] = {
        "status": "preview",
        "document_id": document_id,
        "source_type_id": change.source_type_id,
        "target_type_id": change.target_type_id,
        "matched": len(matches),
        "changed": 0,
        "assignments": [row.model_dump(mode="json") for row in matches],
        "source_removed": False,
        "would_remove_source": change.remove_source_from_ontology,
        "atomic": False,
    }
    if not change.apply:
        return result
    changed = 0
    for row in matches:
        try:
            current = Element.model_validate(await invoke("GET", row.route))
            if current.type_id() != change.source_type_id:
                result.update(status="conflict", stopped_at=row.model_dump(mode="json"))
                return result
            updated = Element.model_validate(
                await invoke(
                    "PATCH", row.route, AssignmentPatch(typology=change.target_type_id)
                )
            )
            if updated.type_id() != change.target_type_id:
                result.update(
                    status="unverified", stopped_at=row.model_dump(mode="json")
                )
                return result
            changed += 1
            result["changed"] = changed
        except (ToolError, ValidationError):
            result.update(
                status="partial_failure",
                stopped_at=row.model_dump(mode="json"),
                message=(
                    "Inspect the stopped record before retrying; "
                    "its write may have completed."
                ),
            )
            return result
    return await finish_replacement(document_id, change, result)


async def finish_replacement(
    document_id: int,
    change: TypeReplacement,
    result: dict[str, JsonValue],
) -> JsonValue:
    """Remove membership only after a fresh scan confirms no source usage."""
    if change.remove_source_from_ontology:
        try:
            remaining = await inventory(document_id, change.kind)
            if any(row.type_id == change.source_type_id for row in remaining):
                result.update(
                    status="conflict",
                    message="Source still used; ontology was not reduced.",
                )
                return result
            latest = await read_ontology(document_id)
            kept = [
                item.pk
                for item in latest.types(change.kind)
                if item.pk != change.source_type_id
            ]
            _ = await invoke(
                "PATCH",
                f"documents/{document_id}/modify_ontology/",
                selection(change.kind, kept),
            )
            verified = await read_ontology(document_id)
            result["source_removed"] = all(
                item.pk != change.source_type_id for item in verified.types(change.kind)
            )
            if not result["source_removed"]:
                result["status"] = "unverified"
                return result
        except (ToolError, ValidationError):
            result.update(
                status="partial_failure",
                message="Assignments processed; re-read ontology to check removal.",
            )
            return result
    result["status"] = "applied"
    return result


def register_repairs(server: MCPServer) -> None:
    """Expose inventories and document-scoped repairs without deleting global types."""

    @server.tool(annotations=READ)
    async def audit_document_ontology(document_id: Identifier) -> JsonValue:
        """Audit type usage, untyped content and invalid/duplicate labels."""
        return await audit(document_id)

    @server.tool(annotations=CHANGE)
    async def replace_ontology_assignments(
        document_id: Identifier,
        change: TypeReplacement,
    ) -> JsonValue:
        """Preview (default) or apply type replacement across an entire document.

        Null source selects untyped content; null target clears assignments.
        Writes are sequential, not atomic; avoid concurrent editing during repair.
        Returns partial progress on failure. Source removal affects this document only.
        """
        return await replace(document_id, change)

    @server.tool(annotations=CHANGE)
    async def merge_ontology_types(
        document_id: Identifier,
        kind: ContentKind,
        source_type_id: Identifier,
        target_type_id: Identifier,
        *,
        apply: bool = False,
    ) -> JsonValue:
        """Preview/apply a merge: reassign usage, then remove source from this document.

        Both definitions remain globally on legacy servers; no global deletion.
        Concurrent edits are not transactionally isolated. Inspect partial results.
        """
        return await replace(
            document_id,
            TypeReplacement(
                kind=kind,
                source_type_id=source_type_id,
                target_type_id=target_type_id,
                remove_source_from_ontology=True,
                apply=apply,
            ),
        )
