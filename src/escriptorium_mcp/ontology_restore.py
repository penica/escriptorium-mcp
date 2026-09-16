"""Additive, conflict-aware restoration of portable ontology definitions."""

from typing import Final

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.api import CREATE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.ontology_models import ContentKind, OntologyType
from escriptorium_mcp.ontology_native import supports_type_color
from escriptorium_mcp.ontology_snapshot import (
    export_snapshot,
    read_components,
    taxonomy_payload,
)
from escriptorium_mcp.ontology_snapshot_models import OntologySnapshot, SnapshotType
from escriptorium_mcp.ontology_tools import read_ontology, selection

KINDS: Final[tuple[ContentKind, ...]] = ("block", "line", "part")


def differences(source: OntologySnapshot, target: OntologySnapshot) -> list[str]:
    """Find conflicts before issuing any write request."""
    conflicts: list[str] = []
    for kind in KINDS:
        existing = {item.name: item for item in target.types(kind)}
        for item in source.types(kind):
            match = existing.get(item.name)
            if match and item.color != match.color:
                conflicts.append(f"{kind} type {item.name!r}: different color")
    components = {item.name: item for item in target.components}
    for component in source.components:
        existing_component = components.get(component.name)
        if existing_component and (
            (existing_component.allowed_values is None)
            != (component.allowed_values is None)
            or set(existing_component.allowed_values or [])
            != set(component.allowed_values or [])
        ):
            conflicts.append(f"component {component.name!r}: different allowed values")
    taxonomies = {item.name: item for item in target.taxonomies}
    for taxonomy in source.taxonomies:
        existing_taxonomy = taxonomies.get(taxonomy.name)
        if existing_taxonomy and (
            existing_taxonomy.model_dump(exclude={"components"})
            != taxonomy.model_dump(exclude={"components"})
            or set(existing_taxonomy.components) != set(taxonomy.components)
        ):
            conflicts.append(f"taxonomy {taxonomy.name!r}: different definition")
    return conflicts


async def attach_type(
    document_id: int,
    kind: ContentKind,
    item: SnapshotType,
    completed: list[str],
) -> None:
    """Create and attach a type; always inspect document-owned IDs afterwards."""
    writable_color = await supports_type_color(kind)
    created = OntologyType.model_validate(
        await call(
            ApiRequest(
                method="POST",
                route=f"types/{kind}/",
                body_json=item.model_dump_json(
                    exclude=set() if writable_color else {"color"}
                ),
            )
        )
    )
    completed.append(f"created/reused {kind} type {item.name!r} ({created.pk})")
    if created.name != item.name or (
        item.color is not None and created.color != item.color
    ):
        msg = "Created/reused type differs from snapshot; attachment stopped."
        raise ValueError(msg)
    latest = await read_ontology(document_id)
    ids = list(dict.fromkeys([t.pk for t in latest.types(kind)] + [created.pk]))
    _ = await invoke(
        "PATCH", f"documents/{document_id}/modify_ontology/", selection(kind, ids)
    )
    refreshed = await read_ontology(document_id)
    assigned = [t for t in refreshed.types(kind) if t.name == item.name]
    if len(assigned) != 1:
        msg = "Attached type was missing or ambiguous after refreshing the document."
        raise ValueError(msg)
    completed.append(f"attached {kind} type {item.name!r} ({assigned[0].pk})")


async def apply_snapshot(
    document_id: int,
    source: OntologySnapshot,
    target: OntologySnapshot,
    completed: list[str],
) -> None:
    """Apply missing definitions in dependency order, recording every success."""
    for kind in KINDS:
        names = {t.name for t in target.types(kind)}
        for item in source.types(kind):
            if item.name not in names:
                await attach_type(document_id, kind, item, completed)
    component_names = {c.name for c in target.components}
    for component in source.components:
        if component.name not in component_names:
            _ = await invoke(
                "POST", f"documents/{document_id}/taxonomies/components/", component
            )
            completed.append(f"created component {component.name!r}")
    components = await read_components(document_id)
    names = [component.name for component in components]
    if len(names) != len(set(names)):
        msg = "Destination component names became ambiguous; taxonomy creation stopped."
        raise ValueError(msg)
    taxonomy_names = {t.name for t in target.taxonomies}
    for taxonomy in source.taxonomies:
        if taxonomy.name not in taxonomy_names:
            payload = taxonomy_payload(taxonomy, components)
            _ = await call(
                ApiRequest(
                    method="POST",
                    route=f"documents/{document_id}/taxonomies/annotations/",
                    body_json=payload.model_dump_json(
                        exclude={"typology"} if payload.typology is None else set()
                    ),
                )
            )
            completed.append(f"created taxonomy {taxonomy.name!r}")


async def restore_snapshot(
    document_id: int,
    snapshot: OntologySnapshot,
    *,
    apply: bool = False,
) -> JsonValue:
    """Preflight all conflicts and capabilities before optional additive writes."""
    target = await export_snapshot(document_id)
    conflicts = differences(snapshot, target)
    planned: list[str] = []
    for kind in KINDS:
        names = {t.name for t in target.types(kind)}
        missing = [item for item in snapshot.types(kind) if item.name not in names]
        planned.extend(f"add {kind} type {item.name!r}" for item in missing)
        if any(item.color is not None for item in missing) and not (
            await supports_type_color(kind)
        ):
            conflicts.append(f"{kind}: destination API cannot write snapshot colors")
    for label, incoming, existing in (
        ("component", snapshot.components, target.components),
        ("taxonomy", snapshot.taxonomies, target.taxonomies),
    ):
        names = {item.name for item in existing}
        planned.extend(
            f"add {label} {item.name!r}" for item in incoming if item.name not in names
        )
    result: dict[str, JsonValue] = {
        "status": "conflict" if conflicts else "preview",
        "scope": "schema-only",
        "planned": list(planned),
        "conflicts": list(conflicts),
        "completed": [],
    }
    if conflicts or not apply:
        return result
    completed: list[str] = []
    try:
        await apply_snapshot(document_id, snapshot, target, completed)
        restored = await export_snapshot(document_id)
        check_restored(snapshot, restored)
    except (ToolError, ValidationError, ValueError, KeyError) as error:
        result["status"] = "partial_failure"
        result["error"] = str(error)
        result["retry_guidance"] = (
            "Inspect or re-export destination before retrying; a failed request may "
            "have completed remotely. No rollback was attempted."
        )
    else:
        result["status"] = "complete"
        result["ontology"] = restored.model_dump(mode="json")
    result["completed"] = list(completed)
    return result


def check_restored(source: OntologySnapshot, target: OntologySnapshot) -> None:
    """Verify all intended names and definitions survived API serialization."""
    missing = (
        any(
            {item.name for item in source.types(kind)}
            - {item.name for item in target.types(kind)}
            for kind in KINDS
        )
        or bool(
            {item.name for item in source.components}
            - {item.name for item in target.components}
        )
        or bool(
            {item.name for item in source.taxonomies}
            - {item.name for item in target.taxonomies}
        )
    )
    if missing or differences(source, target):
        msg = "Destination differs after restoration. Re-export to inspect."
        raise ValueError(msg)


def register_snapshots(server: MCPServer) -> None:
    """Expose portable schema backup and additive restoration."""

    @server.tool(annotations=READ)
    async def export_ontology_snapshot(document_id: Identifier) -> JsonValue:
        """Return versioned JSON ontology schema, excluding annotations/text/geometry.

        Save this result as JSON for backup or pass it to restore_ontology_snapshot.
        Component relations use names, so source database IDs are not required.
        """
        return (await export_snapshot(document_id)).model_dump(mode="json")

    @server.tool(annotations=CREATE)
    async def restore_ontology_snapshot(
        document_id: Identifier,
        snapshot: OntologySnapshot,
        *,
        apply: bool = False,
    ) -> JsonValue:
        """Preview or add portable schema to a document; never delete existing schema.

        Conflicting same-name definitions stop all writes. Apply is non-atomic;
        failures report completed steps. Re-export to inspect state before retrying.
        Annotation instances, text and geometry are not restored by this tool.
        """
        return await restore_snapshot(document_id, snapshot, apply=apply)
