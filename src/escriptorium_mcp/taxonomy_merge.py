"""Preview and apply annotation taxonomy migrations without losing field values."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, JsonValue, ValidationError

from escriptorium_mcp.api import CHANGE, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.taxonomy_state import (
    AnnotationAddress,
    AnnotationState,
    MigrationPatch,
    annotations,
    read_taxonomy,
)


class MergeReport(BaseModel):
    """Progress is explicit because the upstream API has no bulk transaction."""

    status: str = "preview"
    source_taxonomy_id: int
    target_taxonomy_id: int
    annotation_count: int = 0
    changed_routes: list[str] = []
    problems: list[str] = []
    source_deleted: bool = False
    concurrency_note: str = (
        "Pause other writers: upstream has no atomic conditional writes or deletion."
    )


def compatibility(
    source_marker: str,
    target_marker: str,
    target_components: set[int],
    records: list[AnnotationAddress],
) -> list[str]:
    """Reject marker-family changes and unreachable stored component values."""
    problems: list[str] = []
    source_image = source_marker in {"Rectangle", "Polygon"}
    target_image = target_marker in {"Rectangle", "Polygon"}
    if source_image != target_image:
        problems.append("Source and target marker families differ (image versus text).")
    for record in records:
        if (record.kind == "image") != target_image:
            problems.append(f"{record.route}: incompatible target marker family.")
        missing = {value.component_id() for value in record.original.components}
        missing -= target_components
        if missing:
            problems.append(
                f"{record.route}: add component IDs {sorted(missing)} to target first."
            )
    return problems


async def merge_taxonomies(
    document_id: int,
    source_id: int,
    target_id: int,
    *,
    apply: bool = False,
    delete_source: bool = False,
) -> JsonValue:
    """Migrate sequentially, halt on conflict, and retain source unless requested."""
    report = MergeReport(source_taxonomy_id=source_id, target_taxonomy_id=target_id)
    if source_id == target_id:
        report.status = "blocked"
        report.problems.append("Source and target taxonomy IDs must differ.")
        return report.model_dump(mode="json")
    source = await read_taxonomy(document_id, source_id)
    target = await read_taxonomy(document_id, target_id)
    records = await annotations(document_id, source_id)
    report.annotation_count = len(records)
    report.problems = compatibility(
        source.marker_type,
        target.marker_type,
        set(target.definition().components),
        records,
    )
    if report.problems or not apply:
        report.status = "blocked" if report.problems else "preview"
        return report.model_dump(mode="json")
    report.status = "applying"
    try:
        for record in records:
            if (
                await read_taxonomy(document_id, source_id) != source
                or await read_taxonomy(document_id, target_id) != target
            ):
                report.problems.append(
                    "Taxonomy changed since inventory; run preview again."
                )
                break
            current = AnnotationState.model_validate(
                await call(ApiRequest(method="GET", route=record.route))
            )
            if current != record.original:
                report.problems.append(
                    f"{record.route}: annotation changed since inventory."
                )
                break
            patch = MigrationPatch(taxonomy=target_id)
            _ = await call(
                ApiRequest(
                    method="PATCH",
                    route=record.route,
                    body_json=patch.model_dump_json(),
                )
            )
            report.changed_routes.append(record.route)
            updated = AnnotationState.model_validate(
                await call(ApiRequest(method="GET", route=record.route))
            )
            expected = current.model_copy(update={"taxonomy": target_id})
            if updated.model_dump(exclude={"as_w3c"}) != expected.model_dump(
                exclude={"as_w3c"}
            ):
                report.problems.append(
                    f"{record.route}: verification differs; inspect this annotation."
                )
                break
        if not report.problems:
            remaining = await annotations(document_id, source_id)
            if remaining:
                report.problems.append(
                    "Source still has annotations; deletion refused. Run preview again."
                )
            elif delete_source:
                if (
                    await read_taxonomy(document_id, source_id) != source
                    or await read_taxonomy(document_id, target_id) != target
                ):
                    report.problems.append("Taxonomy changed; source deletion refused.")
                else:
                    _ = await call(
                        ApiRequest(
                            method="DELETE",
                            route=(
                                f"documents/{document_id}/taxonomies/annotations/{source_id}/"
                            ),
                        )
                    )
                    report.source_deleted = True
    except (ToolError, ValidationError) as exc:
        report.problems.append(
            f"{type(exc).__name__}: last write may have completed; inspect state."
        )
    report.status = "partial" if report.problems else "completed"
    return report.model_dump(mode="json")


def register_taxonomy_merges(server: MCPServer) -> None:
    """Register an explicit preview-first document annotation taxonomy merge."""

    @server.tool(annotations=CHANGE)
    async def merge_annotation_taxonomies(
        document_id: Identifier,
        source_taxonomy_id: Identifier,
        target_taxonomy_id: Identifier,
        *,
        apply: bool = False,
        delete_source: bool = False,
    ) -> JsonValue:
        """Preview/apply reassignment of all source image/text annotations to target.

        Target must support every stored component and the same marker family.
        Existing values/geometry/text spans remain. Source deletion is opt-in and
        requires a clean rescan. Pause concurrent editing: upstream has no atomic
        conditional writes. Failures return partial progress; inspect before retry.
        """
        return await merge_taxonomies(
            document_id,
            source_taxonomy_id,
            target_taxonomy_id,
            apply=apply,
            delete_source=delete_source,
        )
