"""Metadata inputs distinguish local values, global keys and scoped identities."""

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.metadata_models import (
    MetadataCreate,
    MetadataTarget,
    MetadataValuePatch,
    SharedMetadataKeyPatch,
)


@pytest.mark.parametrize(
    "data",
    [
        {"key": {"name": ""}, "value": "x"},
        {"key": {"name": " "}, "value": "x"},
        {"key": {"name": "x" * 129}, "value": "x"},
        {"key": {"name": None}, "value": "x"},
        {"key": {"name": "k", "cidoc_id": "x" * 9}, "value": "x"},
        {"key": {"name": "k"}, "value": ""},
        {"key": {"name": "k"}, "value": " "},
        {"key": {"name": "k"}, "value": "x" * 513},
        {"key": {"name": "k"}, "value": None},
        {"key": {"name": "k", "public": True}, "value": "x"},
        {"key": {"name": "k"}, "value": "x", "document": 999},
    ],
)
def test_invalid_metadata_create(data: dict[str, JsonValue]) -> None:
    # Given invalid native bounds or an injected writable parent.
    # When parsed, then no valid request model can be constructed.
    with pytest.raises(ValidationError):
        _ = MetadataCreate.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [{}, {"value": None}, {"value": ""}, {"value": "new", "key": {"name": "global"}}],
)
def test_value_patch_cannot_edit_shared_key(changes: dict[str, JsonValue]) -> None:
    # Given an empty, invalid or globally mutating local value patch.
    # When parsed, then it is rejected at the input boundary.
    with pytest.raises(ValidationError):
        _ = MetadataValuePatch.model_validate(changes)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"name": None},
        {"name": ""},
        {"name": "x" * 129},
        {"cidoc_id": "x" * 9},
        {"name": "key", "value": "new"},
    ],
)
def test_shared_key_patch_cannot_include_value(changes: dict[str, JsonValue]) -> None:
    # Given a malformed key edit or the unsafe native combined key/value payload.
    # When parsed, then the dedicated key input rejects it.
    with pytest.raises(ValidationError):
        _ = SharedMetadataKeyPatch.model_validate(changes)


@pytest.mark.parametrize(
    "target",
    [
        {"scope": "document", "document_id": 0},
        {"scope": "document", "document_id": 4, "page_id": 10},
        {"scope": "page", "document_id": 4},
        {"scope": "page", "document_id": 4, "page_id": -1},
        {"scope": "project", "project_id": 1},
    ],
)
def test_metadata_target_is_one_coherent_scope(target: dict[str, JsonValue]) -> None:
    # Given contradictory or incomplete scope identifiers.
    # When parsed, then a valid discriminated target cannot be produced.
    with pytest.raises(ValidationError):
        _ = TypeAdapter[MetadataTarget](MetadataTarget).validate_python(target)


def test_boundary_lengths_and_null_cidoc_are_preserved() -> None:
    # Given maximum native field sizes and a nullable CIDOC edit.
    data = {"key": {"name": "k" * 128, "cidoc_id": "x" * 8}, "value": "v" * 512}
    # When both inputs cross their boundaries.
    created = MetadataCreate.model_validate(data)
    key_patch = SharedMetadataKeyPatch(cidoc_id=None)
    # Then no truncation or conversion from explicit null to omission occurs.
    assert created.model_dump(exclude_unset=True) == data
    assert key_patch.model_dump(exclude_unset=True) == {"cidoc_id": None}
