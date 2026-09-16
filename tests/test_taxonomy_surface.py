"""Exercise taxonomy repair through actual MCP STDIO and HTTP worker requests."""

from copy import deepcopy

import anyio
import pytest
from pydantic import JsonValue

from tests.ontology_fixture import (
    OntologyFixture,
    invoke,
    ontology_fixture,
    ontology_session,
)


def test_taxonomy_edit_and_merge_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    source: dict[str, JsonValue] = {
        "pk": 1,
        "name": "Source",
        "marker_type": "Rectangle",
        "abbreviation": None,
        "marker_detail": None,
        "has_comments": True,
        "typology": {"pk": 5, "name": "Person"},
        "components": [{"pk": 4, "name": "Name", "allowed_values": []}],
    }
    target = deepcopy(source)
    target.update({"pk": 2, "name": "Target"})
    record: dict[str, JsonValue] = {
        "pk": 70,
        "taxonomy": 1,
        "part": 10,
        "comments": "Keep this",
        "coordinates": [[10, 20], [30, 40]],
        "components": [
            {"pk": 6, "component": {"pk": 4, "name": "Name"}, "value": "Alice"}
        ],
    }
    original = deepcopy(record)

    def respond(
        fixture: OntologyFixture,
        method: str,
        path: str,
        body: JsonValue,
    ) -> tuple[int, JsonValue]:
        fixture.requests.append((method, path, body))
        if "/taxonomies/annotations/" in path:
            taxonomy = source if path.endswith("/1/") else target
            if method == "PATCH":
                assert isinstance(body, dict)
                assert body["components"] == [4]
                assert body["typology"] == {"name": "Person"}
                taxonomy.update(
                    {
                        key: value
                        for key, value in body.items()
                        if key not in {"components", "typology"}
                    }
                )
            return 200, taxonomy
        if path == "/api/documents/7/parts/":
            return 200, {"count": 2, "next": None, "results": [{"pk": 10}, {"pk": 20}]}
        if path.endswith("/text/") or "/20/" in path:
            return 200, []
        if path.endswith("/image/"):
            return 200, [record]
        if path.endswith("/image/70/"):
            if method == "PATCH":
                assert isinstance(body, dict)
                assert body["components"] == []
                record["taxonomy"] = body["taxonomy"]
            return 200, record
        return 404, {"detail": "Unknown test endpoint"}

    monkeypatch.setattr(OntologyFixture, "respond", respond)

    async def exercise() -> None:
        with ontology_fixture() as fixture:
            async with ontology_session(fixture) as session:
                _ = await invoke(
                    session,
                    "patch_annotation_taxonomy",
                    {
                        "document_id": 7,
                        "taxonomy_id": 1,
                        "changes": {"name": "Renamed"},
                    },
                )
                patch = fixture.requests[-1]
                assert patch[0] == "PATCH"
                assert isinstance(patch[2], dict)
                assert patch[2]["abbreviation"] is None
                assert patch[2]["marker_detail"] is None
                assert patch[2]["has_comments"] is True
                assert source["name"] == "Renamed"
                fixture.requests.clear()
                preview = await invoke(
                    session,
                    "merge_annotation_taxonomies",
                    {
                        "document_id": 7,
                        "source_taxonomy_id": 1,
                        "target_taxonomy_id": 2,
                    },
                )
                assert isinstance(preview, dict)
                assert preview["status"] == "preview"
                assert preview["annotation_count"] == 1
                assert all(row[0] == "GET" for row in fixture.requests)
                assert any(
                    "/20/annotations/text/" in row[1] for row in fixture.requests
                )
                result = await invoke(
                    session,
                    "merge_annotation_taxonomies",
                    {
                        "document_id": 7,
                        "source_taxonomy_id": 1,
                        "target_taxonomy_id": 2,
                        "apply": True,
                    },
                )
                assert isinstance(result, dict)
                assert result["status"] == "completed"
                assert result["source_deleted"] is False
                assert record == {**original, "taxonomy": 2}
                assert [row[0] for row in fixture.requests if row[0] != "GET"] == [
                    "PATCH"
                ]

    anyio.run(exercise)
