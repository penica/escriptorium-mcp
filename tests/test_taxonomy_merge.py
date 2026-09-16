"""Taxonomy migrations preserve values and stop on unsafe changes."""

from functools import partial
from typing import Literal

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp import taxonomy_merge, taxonomy_state
from escriptorium_mcp.api import ApiRequest


def exercise(
    monkeypatch: pytest.MonkeyPatch,
    *,
    apply: bool = False,
    scenario: Literal["normal", "missing", "conflict", "failure", "new"] = "normal",
    delete_source: bool = False,
) -> tuple[JsonValue, list[ApiRequest]]:
    writes: list[ApiRequest] = []
    moved = False

    async def fake_call(request: ApiRequest) -> JsonValue:
        nonlocal moved
        if request.method != "GET":
            writes.append(request)
            moved = True
            if scenario == "failure":
                msg = "Simulated uncertain HTTP write failure"
                raise ToolError(msg)
            return {"ok": True}
        if "taxonomies" in request.route:
            pk = int(request.route.rstrip("/").split("/")[-1])
            return {
                "pk": pk,
                "name": "People",
                "marker_type": "Rectangle",
                "abbreviation": "P",
                "marker_detail": "",
                "has_comments": True,
                "typology": None,
                "components": [] if scenario == "missing" and pk == 2 else [{"pk": 4}],
            }
        if request.route.endswith("/parts/"):
            return {"results": [{"pk": 9}, {"pk": 10}]}
        if "/text/" in request.route or "/10/" in request.route:
            return []
        row: JsonValue = {
            "pk": 7,
            "taxonomy": 2 if moved else 1,
            "components": [{"component": {"pk": 4}, "value": "Alice"}],
            "coordinates": [[1, 2], [3, 4]],
            "as_w3c": {"body": "target" if moved else "source"},
            "comments": "changed"
            if scenario == "conflict" and request.route.endswith("/7/")
            else "original",
        }
        if scenario == "new" and moved and request.route.endswith("/image/"):
            return [{"pk": 8, "taxonomy": 1, "components": []}]
        return row if request.route.endswith("/7/") else [row]

    monkeypatch.setattr(taxonomy_merge, "call", fake_call)
    monkeypatch.setattr(taxonomy_state, "call", fake_call)
    result = anyio.run(
        partial(
            taxonomy_merge.merge_taxonomies,
            1,
            1,
            2,
            apply=apply,
            delete_source=delete_source,
        )
    )
    return result, writes


def test_preview_never_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    result, writes = exercise(monkeypatch)
    assert isinstance(result, dict)
    assert result["status"] == "preview"
    assert result["annotation_count"] == 1
    assert not writes


def test_apply_preserves_values_then_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    result, writes = exercise(monkeypatch, apply=True, delete_source=True)
    assert isinstance(result, dict)
    assert result["status"] == "completed"
    assert result["source_deleted"] is True
    assert [write.method for write in writes] == ["PATCH", "DELETE"]
    assert TypeAdapter(dict[str, JsonValue]).validate_json(writes[0].body_json) == {
        "taxonomy": 2,
        "components": [],
    }


@pytest.mark.parametrize("flag", ["missing", "conflict"])
def test_unsafe_merge_stops(
    monkeypatch: pytest.MonkeyPatch, flag: Literal["missing", "conflict"]
) -> None:
    result, writes = exercise(monkeypatch, apply=True, scenario=flag)
    assert isinstance(result, dict)
    assert result["status"] in {"blocked", "partial"}
    assert result["problems"]
    assert not writes


def test_marker_family_mismatch() -> None:
    assert taxonomy_merge.compatibility("Rectangle", "Bold", set(), [])


def test_uncertain_write_reports_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    result, writes = exercise(
        monkeypatch, apply=True, scenario="failure", delete_source=True
    )
    assert isinstance(result, dict)
    assert result["status"] == "partial"
    assert result["source_deleted"] is False
    assert len(writes) == 1
    assert writes[0].method == "PATCH"
    assert "may have completed" in str(result["problems"])


def test_rescan_prevents_cascading_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    result, writes = exercise(
        monkeypatch, apply=True, scenario="new", delete_source=True
    )
    assert isinstance(result, dict)
    assert result["status"] == "partial"
    assert result["source_deleted"] is False
    assert (
        len(result["changed_routes"]) == 1
        if isinstance(result["changed_routes"], list)
        else False
    )
    assert [write.method for write in writes] == ["PATCH"]
