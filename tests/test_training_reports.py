"""Training reports retain raw metrics without inferring success or attribution."""

from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import anyio
import pytest

from tests.ontology_fixture import invoke
from tests.training_fixture import TrainingFixture, training_fixture, training_session

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize("score", [None, 0.0, 98.5])
def test_model_only_report_preserves_nullable_and_zero_scores(
    score: float | None,
) -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(session, "get_training_report", {"model_id": 7})
            assert isinstance(result, dict)
            assert result["model_id"] == 7
            assert result["name"] is None
            assert result["job"] == "Recognize"
            assert result["training"] is False
            assert result["accuracy_percent"] == score
            assert result["current_file"] == fixture.model["file"]
            assert result["checkpoints"] == []
            assert result["artifact_availability"] == "not_checked"
            assert result["task_status"] is None
            assert result["task_model_link"] == "not_requested"
            assert "completed" not in result

    with training_fixture() as fixture:
        fixture.model.update(
            {
                "accuracy_percent": score,
                "file": fixture.url + "media/model.safetensors",
                "versions": [],
            }
        )
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", "/api/models/7/", None)]


def test_training_report_preserves_repeated_checkpoint_files_and_zero_metrics() -> None:
    versions: list[JsonValue] = [
        {
            "revision": "first",
            "data": {
                "file": "models/hash/same.ckpt",
                "training_epoch": 0,
                "training_accuracy": 0.0,
                "training_total": 0,
                "training_errors": 0,
            },
        },
        {
            "revision": "second",
            "data": {
                "file": "models/hash/same.ckpt",
                "training_epoch": 1,
                "training_accuracy": None,
            },
            "custom": "retain",
        },
    ]

    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(session, "get_training_report", {"model_id": 7})
            assert isinstance(result, dict)
            assert result["checkpoints"] == versions
            assert result["training"] is None
            assert result["accuracy_percent"] is None
            assert result["artifact_availability"] == "not_checked"

    with training_fixture() as fixture:
        fixture.model.update({"versions": versions, "training": None})
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", "/api/models/7/", None)]


@pytest.mark.parametrize(
    ("job", "method"),
    [("Recognize", "train"), ("Segment", "segtrain"), (1, "segtrain"), (2, "train")],
)
def test_task_status_is_filtered_and_linked_only_by_caller(
    job: str | int, method: str
) -> None:
    wanted: JsonValue = {
        "pk": 5,
        "workflow_state": 2,
        "method": "core.tasks." + method,
        "messages": "fixture failure details",
    }

    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await invoke(
                session,
                "get_training_report",
                {"model_id": 7, "document_id": 4, "group_id": 2},
            )
            assert isinstance(result, dict)
            assert result["task_model_link"] == "caller_supplied"
            assert result["job"] == job
            status = result["task_status"]
            assert isinstance(status, dict)
            assert status["reports"] == [wanted]
            assert status["has_failures"] is True
            assert status["all_finished"] is False
            assert status["total"] == 1

    with training_fixture() as fixture:
        fixture.model["job"] = job
        fixture.reports[:] = [
            wanted,
            {"pk": 6, "workflow_state": 3, "method": "imports.tasks.document_import"},
        ]
        anyio.run(run, fixture)
    assert all(verb == "GET" for verb, _route, _body in fixture.requests)
    query = parse_qs(urlsplit(fixture.requests[-1][1]).query)
    assert query["document"] == ["4"]
    assert query["group"] == ["2"]


def test_group_without_document_is_rejected_before_reads() -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await session.call_tool(
                "get_training_report", {"model_id": 7, "group_id": 2}
            )
            assert result.is_error

    with training_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


def test_wrong_group_backend_error_is_not_reported_as_empty_success() -> None:
    async def run(fixture: TrainingFixture) -> None:
        async with training_session(fixture) as session:
            result = await session.call_tool(
                "get_training_report", {"model_id": 7, "document_id": 4, "group_id": 99}
            )
            assert result.is_error

    with training_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("GET", "/api/documents/4/task_groups/99/", None)
    assert not any(
        route.startswith("/api/tasks/") for _verb, route, _body in fixture.requests
    )
