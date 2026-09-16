import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.job_models import RecognitionTraining, SegmentationTraining


@pytest.mark.parametrize("training", [RecognitionTraining, SegmentationTraining])
@pytest.mark.parametrize("field", ["model", "model_name"])
def test_training_rejects_explicit_null_options(
    training: type[RecognitionTraining] | type[SegmentationTraining], field: str
) -> None:
    # Given an otherwise valid request with an explicit null optional field.
    values: dict[str, JsonValue] = {"parts": [1, 2], "model": 7, "model_name": "Copy"}
    if training is RecognitionTraining:
        values["transcription"] = 3
    values[field] = None
    # When training inputs are parsed, then null is rejected before submission.
    with pytest.raises(ValidationError):
        _ = training.model_validate(values)


@pytest.mark.parametrize("training", [RecognitionTraining, SegmentationTraining])
def test_training_rejects_duplicate_pages(
    training: type[RecognitionTraining] | type[SegmentationTraining],
) -> None:
    # Given duplicate page IDs that should not silently change training selection.
    values: dict[str, JsonValue] = {"parts": [1, 2, 2], "model_name": "Copy"}
    if training is RecognitionTraining:
        values["transcription"] = 3
    # When training inputs are parsed, then duplicate pages are rejected.
    with pytest.raises(ValidationError):
        _ = training.model_validate(values)


def test_training_accepts_database_length_name_without_sending_absent_options() -> None:
    # Given a model name at the server's 256-character database limit.
    values = {"parts": [1, 2], "model_name": "n" * 256}
    # When the input is parsed and serialized, then omitted options stay omitted.
    parsed = SegmentationTraining.model_validate(values)
    assert parsed.model_dump(exclude_unset=True) == values
