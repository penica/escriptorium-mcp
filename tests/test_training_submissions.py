"""Protocol tests for accepted training and uncertain monitoring attribution."""

from typing import Literal

import anyio
import pytest
from pydantic import JsonValue

from tests.ontology_fixture import invoke
from tests.training_fixture import TrainingFixture, training_fixture, training_session


@pytest.mark.parametrize(
    ("tool", "label", "action"),
    [
        ("train_recognition", "Recognize", "train"),
        ("train_segmentation", "Segment", "segtrain"),
    ],
)
def test_untracked_training_preserves_response_and_supported_payload(
    tool: str,
    label: str,
    action: str,
) -> None:
    job: dict[str, JsonValue] = {"parts": [10, 11], "model": 7}
    if action == "train":
        job["transcription"] = 6

    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(session, tool, {"document_id": 4, "job": job})
            assert result == {"status": "ok"}

    with training_fixture() as fixture:
        fixture.model["job"] = label
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", "/api/models/7/", None),
        ("POST", f"/api/documents/4/{action}/", job),
    ]


@pytest.mark.parametrize(
    ("groups", "status", "candidate_ids"),
    [
        ([], "none", []),
        ([{"pk": 3, "method": "core.tasks.train"}], "candidate", [3]),
        ([{"pk": 3, "method": None}], "candidate", [3]),
        (
            [{"pk": 3, "method": "core.tasks.train"}, {"pk": 4, "method": None}],
            "ambiguous",
            [3, 4],
        ),
        ([{"pk": 3, "method": "core.tasks.segtrain"}], "none", []),
    ],
)
def test_tracking_reports_only_new_matching_or_unknown_candidates(
    groups: list[JsonValue],
    status: str,
    candidate_ids: list[int],
) -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(
                session,
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {"parts": [10], "model": 7, "transcription": 6},
                    "track": True,
                },
            )
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"status": "ok"}
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == status
            assert tracking["attribution_confirmed"] is False
            candidates = tracking["candidates"]
            assert isinstance(candidates, list)
            assert [
                row["pk"] for row in candidates if isinstance(row, dict)
            ] == candidate_ids
            assert candidates == (groups if candidate_ids else [])

    with training_fixture() as fixture:
        fixture.groups_after[:] = fixture.groups_before + groups
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _route, _body in fixture.requests) == 1


@pytest.mark.parametrize("scenario", ["before_failure", "after_failure"])
def test_monitoring_failure_keeps_accepted_submission_without_retry(
    scenario: Literal["before_failure", "after_failure"],
) -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(
                session,
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {"parts": [10], "model": 7, "transcription": 6},
                    "track": True,
                },
            )
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"status": "ok"}
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == "unavailable"
            assert tracking["attribution_confirmed"] is False

    with training_fixture(scenario) as fixture:
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _route, _body in fixture.requests) == 1


def test_rejected_training_propagates_error_and_skips_followup_monitoring() -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await session.call_tool(
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {"parts": [10], "model": 7, "transcription": 6},
                    "track": True,
                },
            )
            assert result.is_error

    with training_fixture("post_failure") as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1][0] == "POST"
    assert sum(method == "POST" for method, _route, _body in fixture.requests) == 1


@pytest.mark.parametrize(
    "job",
    [
        {"parts": [10, 10], "model": 7},
        {"parts": [10], "model": None, "model_name": "New"},
        {"parts": [10], "model": 7, "model_name": None},
        {"parts": [10], "model_name": "N" * 257},
    ],
)
def test_invalid_training_fields_never_reach_backend(job: dict[str, JsonValue]) -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await session.call_tool(
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {**job, "transcription": 6},
                },
            )
            assert result.is_error

    with training_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


def test_maximum_model_name_is_accepted() -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(
                session,
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {"parts": [10], "model_name": "N" * 256, "transcription": 6},
                },
            )
            assert result == {"status": "ok"}

    with training_fixture() as fixture:
        anyio.run(run, fixture)
    assert [method for method, _route, _body in fixture.requests] == ["POST"]


@pytest.mark.parametrize(
    "model",
    [
        {"job": "Segment", "rights": "owner", "training": False},
        {"job": "Recognize", "rights": "user", "training": False},
        {"job": "Recognize", "rights": "owner", "training": True},
        {"job": "Recognize", "rights": "owner"},
    ],
)
def test_invalid_override_never_submits_even_with_new_name(
    model: dict[str, JsonValue],
) -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await session.call_tool(
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {
                        "parts": [10],
                        "model": 7,
                        "model_name": "Named",
                        "override": True,
                        "transcription": 6,
                    },
                },
            )
            assert result.is_error

    with training_fixture() as fixture:
        fixture.model.clear()
        fixture.model.update({"pk": 7, **model})
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", "/api/models/7/", None)]


@pytest.mark.parametrize("job_label", ["Recognize", "Segment"])
def test_clone_requires_matching_job_but_not_ownership(job_label: str) -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await session.call_tool(
                "train_recognition",
                {
                    "document_id": 4,
                    "job": {"parts": [10], "model": 7, "transcription": 6},
                },
            )
            assert result.is_error is (job_label != "Recognize")

    with training_fixture() as fixture:
        fixture.model.update({"rights": "public", "job": job_label})
        anyio.run(run, fixture)
    assert [method for method, _route, _body in fixture.requests] == (
        ["GET", "POST"] if job_label == "Recognize" else ["GET"]
    )
