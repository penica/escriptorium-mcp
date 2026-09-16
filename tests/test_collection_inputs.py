"""Collection input models distinguish omission, clearing and invalid references."""

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from escriptorium_mcp.collection_models import CollectionCreate, CollectionPatch


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CollectionCreate, {"name": "N" * 513}),
        (CollectionCreate, {"name": "  "}),
        (CollectionCreate, {"name": None}),
        (CollectionCreate, {"name": "A", "owner": "other"}),
        (CollectionCreate, {"name": "A", "items_to_save": []}),
        (CollectionPatch, {}),
        (CollectionPatch, {"name": None}),
        (CollectionPatch, {"items": None}),
        (CollectionPatch, {"default_transcriptions": None}),
        (CollectionPatch, {"default_transcriptions": {"04": 2}}),
        (CollectionPatch, {"default_transcriptions": {"0": 2}}),
        (CollectionPatch, {"default_transcriptions": {"-4": 2}}),
        (CollectionPatch, {"default_transcriptions": {"document": 2}}),
        (CollectionPatch, {"default_transcriptions": {"4": "2"}}),
        (CollectionPatch, {"default_transcriptions": {"4": True}}),
        (CollectionPatch, {"default_transcriptions": {"4": 0}}),
        (
            CollectionPatch,
            {"items": [{"document_id": 4, "page_id": 0, "transcription_id": 2}]},
        ),
        (
            CollectionPatch,
            {"items": [{"document_id": True, "page_id": 11, "transcription_id": 2}]},
        ),
        (
            CollectionPatch,
            {"items": [{"document_id": 4, "page_id": "11", "transcription_id": 2}]},
        ),
        (
            CollectionPatch,
            {"items": [{"document_id": 4, "page_id": 11, "transcription_id": None}]},
        ),
        (
            CollectionPatch,
            {
                "items": [
                    {"document_id": 4, "page_id": 11, "transcription_id": 2},
                    {"document_id": 8, "page_id": 11, "transcription_id": 19},
                ]
            },
        ),
    ],
)
def test_invalid_collection_inputs(
    model: type[BaseModel], payload: dict[str, JsonValue]
) -> None:
    # Given unsupported ownership, noncanonical references, nulls or duplicate pages.
    # When parsing native collection input, then no valid write model is constructed.
    with pytest.raises(ValidationError):
        _ = model.model_validate(payload)


def test_native_name_boundary_and_empty_clears_are_distinct_from_omission() -> None:
    # Given a maximum-length name with optional fields left out.
    created = CollectionCreate.model_validate({"name": "N" * 512})
    # When serializing caller-supplied fields, then no membership defaults are injected.
    assert created.model_dump(exclude_unset=True) == {"name": "N" * 512}
    cleared = CollectionPatch.model_validate(
        {"items": [], "default_transcriptions": {}}
    )
    assert cleared.model_dump(exclude_unset=True) == {
        "items": [],
        "default_transcriptions": {},
    }
