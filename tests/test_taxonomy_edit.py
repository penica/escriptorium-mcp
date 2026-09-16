"""Partial taxonomy edits preserve upstream replacement relations."""

import anyio
import pytest
from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp import taxonomy_edit
from escriptorium_mcp.api import ApiRequest


def test_partial_edit_preserves_relations(monkeypatch: pytest.MonkeyPatch) -> None:

    writes: list[ApiRequest] = []

    async def fake_call(request: ApiRequest) -> JsonValue:
        if request.method == "GET":
            return {
                "pk": 1,
                "name": "Old",
                "marker_type": "Bold",
                "abbreviation": "B",
                "marker_detail": "",
                "has_comments": True,
                "typology": {"pk": 7, "name": "Person"},
                "components": [{"pk": 4, "name": "Name", "allowed_values": []}],
            }
        writes.append(request)
        return {"ok": True}

    monkeypatch.setattr(taxonomy_edit, "call", fake_call)
    _ = anyio.run(
        taxonomy_edit.patch_taxonomy, 2, 1, taxonomy_edit.TaxonomyPatch(name="New")
    )

    body = TypeAdapter(dict[str, JsonValue]).validate_json(writes[0].body_json)
    assert body["components"] == [4]
    assert body["typology"] == {"name": "Person"}
    assert body["has_comments"] is True
    assert body["name"] == "New"
    _ = anyio.run(
        taxonomy_edit.patch_taxonomy, 2, 1, taxonomy_edit.TaxonomyPatch(typology=None)
    )
    assert "typology" not in TypeAdapter(dict[str, JsonValue]).validate_json(
        writes[1].body_json
    )


@pytest.mark.parametrize("initial", [None, "X"])
def test_nullable_display_fields_preserved_or_cleared(
    monkeypatch: pytest.MonkeyPatch,
    initial: str | None,
) -> None:
    writes: list[ApiRequest] = []

    async def fake_call(request: ApiRequest) -> JsonValue:
        if request.method == "GET":
            return {
                "pk": 1,
                "name": "Old",
                "marker_type": "Rectangle",
                "abbreviation": initial,
                "marker_detail": initial,
                "has_comments": False,
                "typology": None,
                "components": [],
            }
        writes.append(request)
        return {"ok": True}

    monkeypatch.setattr(taxonomy_edit, "call", fake_call)
    changes = (
        taxonomy_edit.TaxonomyPatch(name="New")
        if initial is None
        else (taxonomy_edit.TaxonomyPatch(abbreviation=None, marker_detail=None))
    )
    _ = anyio.run(taxonomy_edit.patch_taxonomy, 2, 1, changes)
    body = TypeAdapter(dict[str, JsonValue]).validate_json(writes[0].body_json)
    assert body["abbreviation"] is None
    assert body["marker_detail"] is None
    assert "typology" not in body
