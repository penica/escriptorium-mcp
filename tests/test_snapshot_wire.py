import anyio
import pytest
from pydantic import JsonValue

from escriptorium_mcp.ontology_snapshot_models import OntologySnapshot
from tests.ontology_fixture import (
    OntologyFixture,
    invoke,
    ontology_fixture,
    ontology_session,
)


def test_snapshot_reads_paginated_collections_over_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = OntologyFixture.collection_response

    def collection(fixture: OntologyFixture, path: str) -> JsonValue:
        if "/taxonomies/components/" in path:
            second = "?page=2" in path
            return {
                "count": 2,
                "previous": None,
                "next": None
                if second
                else (f"{fixture.url}api/documents/7/taxonomies/components/?page=2"),
                "results": [
                    {
                        "pk": 102 if second else 101,
                        "name": "Place" if second else "Date",
                        "allowed_values": None,
                    }
                ],
            }
        if "/taxonomies/annotations/" in path:
            return {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "pk": 201,
                        "name": "Entry",
                        "marker_type": "Rectangle",
                        "abbreviation": None,
                        "marker_detail": None,
                        "has_comments": True,
                        "typology": None,
                        "components": [
                            {"pk": 102, "name": "Place", "allowed_values": None}
                        ],
                    }
                ],
            }
        return original(fixture, path)

    monkeypatch.setattr(OntologyFixture, "collection_response", collection)

    async def scenario() -> None:
        with ontology_fixture() as fixture:
            async with ontology_session(fixture) as session:
                raw = await invoke(
                    session, "export_ontology_snapshot", {"document_id": 7}
                )
                snapshot = OntologySnapshot.model_validate(raw)
                assert [item.name for item in snapshot.components] == ["Date", "Place"]
                assert snapshot.taxonomies[0].components == ["Place"]
                assert snapshot.taxonomies[0].abbreviation is None
                result = await invoke(
                    session,
                    "restore_ontology_snapshot",
                    {
                        "document_id": 7,
                        "snapshot": snapshot.model_dump(mode="json"),
                    },
                )
                assert isinstance(result, dict)
                assert result["status"] == "preview"
                assert result["planned"] == []
                assert all(method == "GET" for method, _, _ in fixture.requests)
                assert any("?page=2" in path for _, path, _ in fixture.requests)

    anyio.run(scenario)
