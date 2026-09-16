"""Alignment inputs require explicit strict consent and coherent native options."""

import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.alignment_models import AlignmentJob, ForcedAlignmentJob
from tests.alignment_fixture import alignment_job


@pytest.mark.parametrize("value", [False, None, 1, "true", 0])
def test_target_reuse_ack_requires_exact_true(value: JsonValue) -> None:
    # Given a non-Boolean-true acknowledgment, including coercible values.
    job = alignment_job({"acknowledge_target_reuse": value})
    # When parsed, then explicit target reuse cannot be implied by coercion.
    with pytest.raises(ValidationError):
        _ = AlignmentJob.model_validate(job)


def test_target_reuse_ack_cannot_be_omitted() -> None:
    # Given an otherwise valid job without target-reuse acknowledgment.
    job = alignment_job()
    _ = job.pop("acknowledge_target_reuse")
    # When parsed, then the missing acknowledgment is rejected.
    with pytest.raises(ValidationError):
        _ = AlignmentJob.model_validate(job)


@pytest.mark.parametrize(
    "change",
    [
        {"parts": []},
        {"parts": None},
        {"parts": [10, 10]},
        {"parts": [0]},
        {"region_types": []},
        {"region_types": None},
        {"region_types": [3, 3]},
        {"region_types": ["undefined"]},
        {"layer_name": " "},
        {"layer_name": "x" * 513},
        {"layer_name": None},
        {"n_gram": 1},
        {"n_gram": 26},
        {"n_gram": True},
        {"gap": 0},
        {"gap": 1000001},
        {"threshold": -0.1},
        {"threshold": 1.1},
        {"threshold": float("inf")},
        {"search": {"kind": "beam", "beam_size": 0}},
        {"search": {"kind": "beam", "beam_size": 101}},
        {"search": {"kind": "offset"}},
        {"search": {"kind": "offset", "max_offset": 81}},
        {"search": {"kind": "offset", "max_offset": 1, "beam_size": 20}},
        {"witness": {"kind": "existing", "witness_id": 7, "file_path": "/unused.txt"}},
    ],
)
def test_invalid_alignment_options(change: dict[str, JsonValue]) -> None:
    # Given invalid boundaries, ambiguous selections or contradictory modes.
    # When parsed, then no native request can be formed.
    with pytest.raises(ValidationError):
        _ = AlignmentJob.model_validate(alignment_job(change))


@pytest.mark.parametrize(
    "change",
    [
        {"parts": []},
        {"parts": None},
        {"parts": [10, 10]},
        {"model": None},
        {"transcription": 0},
        {"layer_name": "new"},
        {"witness": {"kind": "existing", "witness_id": 7}},
        {"threshold": 0.8},
    ],
)
def test_forced_alignment_accepts_only_model_layer_and_optional_pages(
    change: dict[str, JsonValue],
) -> None:
    # Given ordinary alignment controls or invalid native IDs in a forced job.
    job: dict[str, JsonValue] = {"model": 8, "transcription": 2, **change}
    # When parsed, then unsupported fields cannot be forwarded.
    with pytest.raises(ValidationError):
        _ = ForcedAlignmentJob.model_validate(job)


def test_target_layer_name_is_trimmed_before_scope_comparison() -> None:
    # Given the native maximum-length name with surrounding whitespace.
    job = alignment_job({"layer_name": "  " + "x" * 512 + "  "})
    # When parsed, native trimming occurs before maximum-length validation.
    result = AlignmentJob.model_validate(job)
    # Then the value used for scope checks matches native serializer semantics.
    assert result.layer_name == "x" * 512
