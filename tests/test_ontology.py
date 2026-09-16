import anyio
import pytest
from pydantic import JsonValue

from tests.ontology_fixture import invoke, ontology_fixture, ontology_session


def test_ontology_definitions_and_selections() -> None:
    async def exercise() -> None:
        with ontology_fixture() as fixture:
            async with ontology_session(fixture) as session:
                _ = await invoke(session, "list_ontology_types", {"kind": "line"})
                _ = await invoke(
                    session,
                    "create_ontology_type",
                    {"kind": "line", "data": {"name": "New"}},
                )
                _ = await invoke(
                    session,
                    "update_ontology_type",
                    {"kind": "line", "type_id": 80, "changes": {"name": "Renamed"}},
                )
                _ = await invoke(
                    session, "delete_ontology_type", {"kind": "line", "type_id": 80}
                )
                _ = await invoke(
                    session,
                    "set_document_ontology",
                    {"document_id": 7, "types": {"valid_block_types": []}},
                )
                assert fixture.ontology["valid_block_types"] == []
                assert fixture.ontology["valid_part_types"] == [
                    {"pk": 1, "name": "Page"}
                ]
                assert fixture.requests[-1][2] == {"valid_block_types": []}
                result = await invoke(
                    session,
                    "add_document_ontology_type",
                    {"document_id": 7, "kind": "line", "data": {"name": "Added"}},
                )
                assert isinstance(result, dict)
                assert result["valid_line_types"] == [
                    {"pk": 3, "name": "3"},
                    {"pk": 4, "name": "4"},
                    {"pk": 81, "name": "Added"},
                ]
                writes = [row for row in fixture.requests if row[0] != "GET"]
                assert writes[:3] == [
                    ("POST", "/api/types/line/", {"name": "New"}),
                    ("PATCH", "/api/types/line/80/", {"name": "Renamed"}),
                    ("DELETE", "/api/types/line/80/", {}),
                ]

    anyio.run(exercise)


def test_audit_and_merge_preview_are_read_only() -> None:
    async def exercise() -> None:
        with ontology_fixture() as fixture:
            async with ontology_session(fixture) as session:
                report = await invoke(
                    session, "audit_document_ontology", {"document_id": 7}
                )
                assert isinstance(report, dict)
                lines = report["line"]
                assert isinstance(lines, dict)
                assert lines["total"] == 3
                assert lines["duplicate_labels"] == [[3, 4]]
                outside = lines["outside_ontology"]
                assert isinstance(outside, list)
                assert len(outside) == 1
                part = report["part"]
                assert isinstance(part, dict)
                assert part["untyped"] == 1
                preview = await invoke(
                    session,
                    "merge_ontology_types",
                    {
                        "document_id": 7,
                        "kind": "line",
                        "source_type_id": 3,
                        "target_type_id": 4,
                    },
                )
                assert isinstance(preview, dict)
                assert preview["status"] == "preview"
                assert preview["matched"] == 2
                assert preview["changed"] == 0
                assert all(method == "GET" for method, _, _ in fixture.requests)

    anyio.run(exercise)


@pytest.mark.parametrize(
    ("mode", "expected", "changed"),
    [
        ("normal", "applied", 2),
        ("failure", "partial_failure", 1),
        ("conflict", "conflict", 0),
    ],
)
def test_merge_preserves_membership_until_assignments_succeed(
    mode: str, expected: str, changed: int
) -> None:
    async def exercise() -> None:
        with ontology_fixture(mode) as fixture:
            async with ontology_session(fixture) as session:
                result = await invoke(
                    session,
                    "merge_ontology_types",
                    {
                        "document_id": 7,
                        "kind": "line",
                        "source_type_id": 3,
                        "target_type_id": 4,
                        "apply": True,
                    },
                )
                assert isinstance(result, dict)
                assert result["status"] == expected
                assert result["changed"] == changed
                patches = [
                    (path, body)
                    for method, path, body in fixture.requests
                    if method == "PATCH"
                ]
                assignments = [body for path, body in patches if "/lines/" in path]
                assert all(body == {"typology": 4} for body in assignments)
                removals = [body for path, body in patches if "modify_ontology" in path]
                if expected == "applied":
                    assert removals == [{"valid_line_types": [4]}]
                    assert result["source_removed"] is True
                else:
                    assert removals == []
                    assert fixture.ontology["valid_line_types"] == [
                        {"pk": 3, "name": "Body"},
                        {"pk": 4, "name": " body "},
                    ]

    anyio.run(exercise)


@pytest.mark.parametrize("target", [99, 0])
def test_invalid_target_never_writes(target: int) -> None:
    async def exercise() -> None:
        with ontology_fixture() as fixture:
            async with ontology_session(fixture) as session:
                result = await session.call_tool(
                    "merge_ontology_types",
                    {
                        "document_id": 7,
                        "kind": "line",
                        "source_type_id": 3,
                        "target_type_id": target,
                        "apply": True,
                    },
                )
                assert result.is_error
                assert all(method == "GET" for method, _, _ in fixture.requests)

    anyio.run(exercise)


@pytest.mark.parametrize("types", [{}, {"valid_line_types": [3, 3]}])
def test_invalid_ontology_lists_never_call_api(types: dict[str, JsonValue]) -> None:
    async def exercise() -> None:
        with ontology_fixture() as fixture:
            async with ontology_session(fixture) as session:
                result = await session.call_tool(
                    "set_document_ontology", {"document_id": 7, "types": types}
                )
                assert result.is_error
                assert fixture.requests == []

    anyio.run(exercise)
