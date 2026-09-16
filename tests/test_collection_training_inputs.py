"""Collection training input omits document-only and unsupported controls."""

import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.collection_training_models import CollectionTraining


@pytest.mark.parametrize(
    "job",
    [
        {},
        {"model": None},
        {"model": None, "model_name": "new"},
        {"model_name": None},
        {"model": 0},
        {"model_name": ""},
        {"model_name": " "},
        {"model_name": "x" * 257},
        {"model": 7, "model_name": None},
        {"model_name": "new", "override": None},
        {"model_name": "new", "parts": [10]},
        {"model_name": "new", "transcription": 2},
        {"model_name": "new", "epochs": 2},
    ],
)
def test_invalid_collection_training_input(job: dict[str, JsonValue]) -> None:
    # Given missing model identity or a document-only/unsupported option.
    # When parsed, then it cannot become a collection training request.
    with pytest.raises(ValidationError):
        _ = CollectionTraining.model_validate(job)


def test_model_name_boundary_and_explicit_false_survive() -> None:
    # Given the maximum model name and an intentional clone/default override value.
    job = {"model_name": "x" * 256, "override": False}
    # When parsed and serialized for the native endpoint.
    result = CollectionTraining.model_validate(job).model_dump(exclude_unset=True)
    # Then no truncation or loss of explicit false occurs.
    assert result == job


def test_omitted_override_stays_omitted() -> None:
    # Given a minimal existing-model request.
    job = CollectionTraining(model=7)
    # When only explicitly supplied native fields are serialized.
    result = job.model_dump(exclude_unset=True)
    # Then neither override nor a synthetic name is inserted.
    assert result == {"model": 7}
