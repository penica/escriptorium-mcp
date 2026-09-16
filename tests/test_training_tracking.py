"""Tracked segmentation and malformed monitoring data retain uncertainty."""

import anyio

from tests.ontology_fixture import invoke
from tests.training_fixture import TrainingFixture, training_fixture, training_session


def test_tracked_segmentation_selects_only_segmentation_candidate() -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(
                session,
                "train_segmentation",
                {
                    "document_id": 4,
                    "job": {"parts": [10, 11], "model": 7},
                    "track": True,
                },
            )
            assert isinstance(result, dict)
            assert result["accepted"] is True
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == "candidate"
            assert tracking["attribution_confirmed"] is False
            assert tracking["candidates"] == [
                {"pk": 3, "method": "core.tasks.segtrain", "custom": "retain"}
            ]

    with training_fixture() as fixture:
        fixture.model.update({"job": "Segment", "rights": "public"})
        fixture.groups_after[:] = [
            *fixture.groups_before,
            {"pk": 3, "method": "core.tasks.segtrain", "custom": "retain"},
            {"pk": 4, "method": "core.tasks.train"},
        ]
        anyio.run(run, fixture)
    assert [route for method, route, _body in fixture.requests if method == "POST"] == [
        "/api/documents/4/segtrain/"
    ]


def test_invalid_after_submission_group_data_keeps_acceptance() -> None:
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
            assert tracking["candidates"] == []

    with training_fixture() as fixture:
        fixture.groups_after[:] = [{"pk": "not-an-id", "method": "core.tasks.train"}]
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _route, _body in fixture.requests) == 1
    assert fixture.requests[-1] == ("GET", "/api/documents/4/task_groups/", None)
