"""Typed page inputs reject unsafe coercions and unsupported writable fields."""

import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.page_models import (
    BulkPageMove,
    CropBox,
    PageByOrder,
    PageFilters,
    Rotation,
)
from escriptorium_mcp.record_models import PagePatch


@pytest.mark.parametrize(
    "angle", [0, 360, -360, True, "90", 1.5, float("inf"), float("nan")]
)
def test_rotation_rejects_unsupported_angles(angle: JsonValue) -> None:
    # Given a value outside the integer nonzero rotation contract.
    # When parsed at the input boundary.
    with pytest.raises(ValidationError):
        _ = Rotation.model_validate({"angle": angle})
    # Then no valid mutation payload exists.


@pytest.mark.parametrize(
    "box",
    [
        {"x1": -1, "y1": 0, "x2": 10, "y2": 10},
        {"x1": 0, "y1": 0, "x2": 0, "y2": 10},
        {"x1": 0, "y1": 5, "x2": 10, "y2": 4},
        {"x1": False, "y1": 0, "x2": 10, "y2": 10},
        {"x1": 0, "y1": 0, "x2": 10.5, "y2": 10},
    ],
)
def test_crop_rejects_invalid_pixel_rectangles(box: dict[str, JsonValue]) -> None:
    # Given coercible, negative, or non-positive-area coordinates.
    # When parsed as a crop rectangle.
    with pytest.raises(ValidationError):
        _ = CropBox.model_validate(box)
    # Then no mutation payload can be constructed.


@pytest.mark.parametrize(
    "move",
    [
        {"page_ids": [], "index": 0},
        {"page_ids": [10, 10], "index": 0},
        {"page_ids": [True], "index": 0},
        {"page_ids": [0], "index": 0},
        {"page_ids": [10], "index": -2},
        {"page_ids": [10], "index": True},
    ],
)
def test_move_rejects_invalid_selection(move: dict[str, JsonValue]) -> None:
    # Given an invalid selection or insertion position.
    # When the bulk move boundary parses it.
    with pytest.raises(ValidationError):
        _ = BulkPageMove.model_validate(move)
    # Then no silently collapsed or coerced selection survives.


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"name": None},
        {"source": None},
        {"original_filename": None},
        {"name": "x" * 513},
        {"source": "x" * 1025},
        {"original_filename": "x" * 1025},
        {"max_avg_confidence": float("inf")},
        {"max_avg_confidence": float("nan")},
        {"order": 3},
        {"image_file_size": 123},
        {"image": "path.png"},
    ],
)
def test_metadata_rejects_invalid_or_read_only_fields(
    patch: dict[str, JsonValue],
) -> None:
    # Given invalid metadata or a field with a dedicated action.
    # When metadata PATCH is parsed.
    with pytest.raises(ValidationError):
        _ = PagePatch.model_validate(patch)
    # Then the unrelated action cannot be smuggled through metadata.


@pytest.mark.parametrize(
    "patch",
    [
        {"name": "", "source": "", "original_filename": ""},
        {"comments": None, "max_avg_confidence": None, "typology": None},
        {"max_avg_confidence": -2.5},
        {"max_avg_confidence": 2.5},
        {"name": "x" * 512, "source": "x" * 1024, "original_filename": "x" * 1024},
    ],
)
def test_metadata_preserves_supported_boundaries(patch: dict[str, JsonValue]) -> None:
    # Given native writable boundary values, including nullable metadata.
    # When parsed and serialized for PATCH.
    result = PagePatch.model_validate(patch).model_dump(mode="json", exclude_unset=True)
    # Then omission and explicit null remain distinct.
    assert result == patch


@pytest.mark.parametrize(
    "filters",
    [{"ordering": []}, {"ordering": ["workflow"]}, {"tag": "x"}, {"ordering": "name"}],
)
def test_filters_reject_unsupported_native_queries(
    filters: dict[str, JsonValue],
) -> None:
    # Given an unsupported or incorrectly shaped query.
    # When parsed at the list boundary.
    with pytest.raises(ValidationError):
        _ = PageFilters.model_validate(filters)
    # Then no invented upstream filter is accepted.


@pytest.mark.parametrize("order", [-1, True, "0", 0.5])
def test_lookup_requires_nonnegative_integer_order(order: JsonValue) -> None:
    # Given an invalid zero-based page position.
    # When parsed for lookup.
    with pytest.raises(ValidationError):
        _ = PageByOrder.model_validate({"document_id": 4, "order": order})
    # Then the order cannot be confused with a coercible value.
