from typing import TYPE_CHECKING

import anyio
import pytest

from tests.mutation_fixture import Case, api_fixture, exercise

if TYPE_CHECKING:
    from pydantic import JsonValue


def case_id(case: Case) -> str:
    return case.tool


@pytest.mark.parametrize(
    "case",
    [
        Case(
            "create_annotation_component",
            {
                "document_id": 7,
                "component": {
                    "name": "Occupation",
                    "allowed_values": ["Farmer", "Miller"],
                },
            },
            "documents/7/taxonomies/components/",
            payload={"name": "Occupation", "allowed_values": ["Farmer", "Miller"]},
        ),
        Case(
            "update_annotation_component",
            {"document_id": 7, "component_id": 2, "changes": {"allowed_values": []}},
            "documents/7/taxonomies/components/2/",
            "PATCH",
            {"allowed_values": []},
        ),
        Case(
            "delete_annotation_component",
            {"document_id": 7, "component_id": 2},
            "documents/7/taxonomies/components/2/",
            "DELETE",
        ),
        Case(
            "create_annotation_taxonomy",
            {
                "document_id": 7,
                "taxonomy": {
                    "name": "Person",
                    "marker_type": "Rectangle",
                    "components": [2],
                    "typology": {"name": "Named entity"},
                },
            },
            "documents/7/taxonomies/annotations/",
            payload={
                "name": "Person",
                "marker_type": "Rectangle",
                "components": [2],
                "typology": {"name": "Named entity"},
                "abbreviation": "",
                "marker_detail": "",
                "has_comments": False,
            },
        ),
        Case(
            "update_annotation_taxonomy",
            {
                "document_id": 7,
                "taxonomy_id": 3,
                "definition": {
                    "name": "Person",
                    "marker_type": "Bold",
                    "components": [],
                    "typology": None,
                },
            },
            "documents/7/taxonomies/annotations/3/",
            "PATCH",
            {
                "name": "Person",
                "marker_type": "Bold",
                "components": [],
                "abbreviation": "",
                "marker_detail": "",
                "has_comments": False,
            },
        ),
        Case(
            "delete_annotation_taxonomy",
            {"document_id": 7, "taxonomy_id": 3},
            "documents/7/taxonomies/annotations/3/",
            "DELETE",
        ),
        Case(
            "update_annotation_taxonomy",
            {
                "document_id": 7,
                "taxonomy_id": 3,
                "definition": {"name": "Accidental rename", "marker_type": "Bold"},
            },
        ),
        Case(
            "create_annotation_taxonomy",
            {
                "document_id": 7,
                "taxonomy": {"name": "Person", "marker_type": "unsupported"},
            },
        ),
        Case(
            "update_annotation_component",
            {"document_id": 7, "component_id": 2, "changes": {}},
        ),
    ],
    ids=case_id,
)
def test_annotation_mutation_when_called_through_mcp(case: Case) -> None:
    with api_fixture() as fixture:
        anyio.run(exercise, fixture, case)


def test_taxonomy_replacement_when_relations_retained() -> None:
    definition: dict[str, JsonValue] = {
        "name": "Renamed person",
        "marker_type": "Text Color",
        "components": [2, 9],
        "typology": {"name": "Named entity"},
        "abbreviation": "PER",
        "marker_detail": "#00ff00",
        "has_comments": True,
    }
    case = Case(
        "update_annotation_taxonomy",
        {"document_id": 7, "taxonomy_id": 3, "definition": definition},
        "documents/7/taxonomies/annotations/3/",
        "PATCH",
        definition,
    )
    with api_fixture() as fixture:
        anyio.run(exercise, fixture, case)
