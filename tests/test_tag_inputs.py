"""Typed tag inputs preserve omitted defaults and reject ignored mutations."""

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.tag_models import TagCreate, TagPatch, TagTarget


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"name": None},
        {"name": "Tag", "color": None},
        {"name": "Tag", "color": ""},
        {"name": "Tag", "color": " "},
        {"name": "Tag", "color": "x" * 8},
        {"name": "Tag", "project": 7},
        {"name": "Tag", "user": 1},
    ],
)
def test_invalid_tag_creation(data: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        _ = TagCreate.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [{}, {"name": None}, {"color": None}, {"name": " "}, {"color": " "}, {"pk": 2}],
)
def test_invalid_tag_patch(changes: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        _ = TagPatch.model_validate(changes)


@pytest.mark.parametrize(
    "target",
    [
        {},
        {"scope": "other"},
        {"scope": "personal_projects", "project_id": 7},
        {"scope": "project_documents"},
        {"scope": "project_documents", "project_id": 0},
        {"scope": "project_documents", "project_id": "7"},
        {"scope": "project_documents", "project_id": True},
        {"scope": "project_documents", "project_id": None},
    ],
)
def test_invalid_tag_scope(target: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        _ = TypeAdapter[TagTarget](TagTarget).validate_python(target)


def test_native_color_and_name_limits_are_preserved() -> None:
    data = TagCreate(name="x" * 100, color="abcdefg")
    assert data.model_dump(exclude_unset=True) == {
        "name": "x" * 100,
        "color": "abcdefg",
    }
    assert TagCreate(name="Tag").model_dump(exclude_unset=True) == {"name": "Tag"}
    assert TagPatch(color="red").model_dump(exclude_unset=True) == {"color": "red"}
