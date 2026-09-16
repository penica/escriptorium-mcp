import anyio
import pytest
from pydantic import ValidationError

from escriptorium_mcp import api, ontology_restore, ontology_snapshot
from escriptorium_mcp.annotation_models import AnnotationComponent
from escriptorium_mcp.ontology_restore import (
    check_restored,
    differences,
    restore_snapshot,
)
from escriptorium_mcp.ontology_snapshot import (
    ComponentRead,
    TaxonomyRead,
    export_snapshot,
)
from escriptorium_mcp.ontology_snapshot_models import (
    OntologySnapshot,
    SnapshotTaxonomy,
    SnapshotType,
)
from tests.snapshot_fixture import SnapshotAPI


def specimen() -> OntologySnapshot:
    return OntologySnapshot(
        valid_block_types=[SnapshotType(name="Body")],
        valid_line_types=[],
        valid_part_types=[],
        components=[AnnotationComponent(name="Date", allowed_values=["1800", "1801"])],
        taxonomies=[
            SnapshotTaxonomy(
                name="Person",
                marker_type="Rectangle",
                abbreviation="P",
                marker_detail="#abcdef",
                has_comments=True,
                typology="Person type",
                components=["Date"],
            )
        ],
    )


def connect(monkeypatch: pytest.MonkeyPatch, fixture: SnapshotAPI) -> None:
    async def legacy_colors(_kind: str) -> bool:
        return False

    monkeypatch.setattr(ontology_restore, "supports_type_color", legacy_colors)
    monkeypatch.setattr(api, "call", fixture.request)
    monkeypatch.setattr(ontology_snapshot, "call", fixture.request)
    monkeypatch.setattr(ontology_restore, "call", fixture.request)


def test_preview_and_apply_roundtrip_remap_destination_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = SnapshotAPI()
    connect(monkeypatch, fixture)

    async def scenario() -> None:
        preview = await restore_snapshot(2, specimen())
        assert isinstance(preview, dict)
        assert preview["status"] == "preview"
        assert not fixture.writes
        applied = await restore_snapshot(2, specimen(), apply=True)
        assert isinstance(applied, dict)
        assert applied["status"] == "complete"
        assert await export_snapshot(2) == specimen()
        assert fixture.document.valid_block_types[0].pk == 107
        count = len(fixture.writes)
        again = await restore_snapshot(2, specimen(), apply=True)
        assert isinstance(again, dict)
        assert again["status"] == "complete"
        assert len(fixture.writes) == count

    anyio.run(scenario)


def test_conflicts_stop_all_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = SnapshotAPI(
        components=[ComponentRead(pk=209, name="Date", allowed_values=["1900"])]
    )
    connect(monkeypatch, fixture)

    async def scenario() -> None:
        result = await restore_snapshot(2, specimen(), apply=True)
        assert isinstance(result, dict)
        assert result["status"] == "conflict"
        assert not fixture.writes

    anyio.run(scenario)


def test_partial_failure_reports_completed_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = SnapshotAPI(fail_taxonomy=True)
    connect(monkeypatch, fixture)

    async def scenario() -> None:
        result = await restore_snapshot(2, specimen(), apply=True)
        assert isinstance(result, dict)
        assert result["status"] == "partial_failure"
        assert result["completed"] == [
            "created/reused block type 'Body' (7)",
            "attached block type 'Body' (107)",
            "created component 'Date'",
        ]
        assert fixture.components
        assert not fixture.taxonomies

    anyio.run(scenario)


def test_snapshot_rejects_ambiguous_or_missing_references() -> None:
    snapshot = specimen().model_dump()
    snapshot["components"] = []
    with pytest.raises(ValidationError, match="undefined"):
        _ = OntologySnapshot.model_validate(snapshot)
    snapshot = specimen().model_dump()
    snapshot["valid_block_types"] = [{"name": "Body"}, {"name": "Body"}]
    with pytest.raises(ValidationError, match="unique"):
        _ = OntologySnapshot.model_validate(snapshot)
    snapshot = specimen().model_dump()
    snapshot["version"] = 2
    with pytest.raises(ValidationError):
        _ = OntologySnapshot.model_validate(snapshot)


def test_missing_post_restore_definition_is_not_success() -> None:
    missing = specimen().model_copy(update={"taxonomies": []})
    with pytest.raises(ValueError, match="differs"):
        check_restored(specimen(), missing)


def test_unsupported_colors_preflight_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = SnapshotAPI()
    connect(monkeypatch, fixture)

    async def unsupported(_kind: str) -> bool:
        return False

    monkeypatch.setattr(ontology_restore, "supports_type_color", unsupported)

    async def scenario() -> None:
        source = specimen().model_copy(
            update={"valid_block_types": [SnapshotType(name="Body", color="#ffffff")]}
        )
        result = await restore_snapshot(2, source, apply=True)
        assert isinstance(result, dict)
        assert result["status"] == "conflict"
        assert not fixture.writes

    anyio.run(scenario)


def test_taxonomy_display_conflict_stops_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = SnapshotAPI(
        taxonomies=[
            TaxonomyRead(
                pk=3,
                name="Person",
                marker_type="Bold",
                components=[],
            )
        ]
    )
    connect(monkeypatch, fixture)

    async def scenario() -> None:
        result = await restore_snapshot(2, specimen(), apply=True)
        assert isinstance(result, dict)
        assert result["status"] == "conflict"
        assert not fixture.writes

    anyio.run(scenario)


def test_nullable_schema_export_restore_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ComponentRead(pk=18, name="Date", allowed_values=None)
    fixture = SnapshotAPI(
        components=[component],
        taxonomies=[
            TaxonomyRead(
                pk=19,
                name="Person",
                marker_type="Rectangle",
                abbreviation=None,
                marker_detail=None,
                components=[component],
            )
        ],
    )
    connect(monkeypatch, fixture)

    async def scenario() -> None:
        snapshot = await export_snapshot(1)
        assert snapshot.components[0].allowed_values is None
        assert snapshot.taxonomies[0].abbreviation is None
        assert snapshot.taxonomies[0].marker_detail is None
        fixture.components.clear()
        fixture.taxonomies.clear()
        restored = await restore_snapshot(2, snapshot, apply=True)
        assert isinstance(restored, dict)
        assert restored["status"] == "complete"
        assert await export_snapshot(2) == snapshot
        assert '"abbreviation":null' in fixture.writes[-1].body_json
        assert '"marker_detail":null' in fixture.writes[-1].body_json
        assert '"allowed_values":null' in fixture.writes[0].body_json

    anyio.run(scenario)


def test_null_and_empty_component_values_are_not_silently_interchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = SnapshotAPI(
        components=[
            ComponentRead(
                pk=209,
                name="Date",
                allowed_values=[],
            )
        ]
    )
    connect(monkeypatch, fixture)

    async def scenario() -> None:
        source = specimen().model_copy(
            update={
                "components": [AnnotationComponent(name="Date", allowed_values=None)],
            }
        )
        result = await restore_snapshot(2, source, apply=True)
        assert isinstance(result, dict)
        assert result["status"] == "conflict"
        assert not fixture.writes

    anyio.run(scenario)


def test_snapshot_null_color_conflicts_with_destination_color() -> None:
    source = specimen()
    target = source.model_copy(
        update={
            "valid_block_types": [SnapshotType(name="Body", color="#aabbcc")],
        }
    )
    assert differences(source, target) == ["block type 'Body': different color"]


def test_modern_restore_explicit_null_color_avoids_server_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = SnapshotAPI()
    connect(monkeypatch, fixture)

    async def modern_colors(_kind: str) -> bool:
        return True

    monkeypatch.setattr(ontology_restore, "supports_type_color", modern_colors)

    async def scenario() -> None:
        result = await restore_snapshot(2, specimen(), apply=True)
        assert isinstance(result, dict)
        assert result["status"] == "complete"
        assert '"color":null' in fixture.writes[0].body_json

    anyio.run(scenario)
