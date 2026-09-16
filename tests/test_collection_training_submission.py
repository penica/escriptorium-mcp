"""Collection training preserves confirmed model IDs and exact native fields."""

import anyio
import pytest
from pydantic import JsonValue

from tests.collection_training_fixture import (
    COLLECTION,
    ITEMS,
    MODEL,
    CollectionTrainingFixture,
    collection_training_fixture,
    collection_training_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("action", ["recognizer", "segmenter"])
@pytest.mark.parametrize(
    "job",
    [
        {"model_name": "new model"},
        {"model": 7},
        {"model": 7, "model_name": "clone", "override": False},
        {"model": 7, "model_name": "overwrite", "override": True},
    ],
)
def test_collection_submission_preserves_native_payload(
    action: str, job: dict[str, JsonValue]
) -> None:
    # Given a collection with selected layers across two source documents.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When all current collection items are submitted for training.
            result = await invoke(
                session, "train_collection_" + action, {"collection_id": 5, "job": job}
            )
            # Then the confirmed model target and extra server fields survive.
            assert result == {"status": "ok", "model_id": 9, "custom": "retained"}

    with collection_training_fixture() as fixture:
        fixture.model["job"] = "Segment" if action == "segmenter" else "Recognize"
        anyio.run(run, fixture)
    assert fixture.requests[-1] == ("POST", COLLECTION + "train_" + action + "/", job)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1
    assert ("GET", ITEMS + "?page=2", None) in fixture.requests
    assert ("GET", "/api/documents/6/transcriptions/3/", None) in fixture.requests
    assert all(
        "task_groups" not in route and not route.startswith("/api/tasks/")
        for _, route, _ in fixture.requests
    )
    assert any(route == MODEL for _, route, _ in fixture.requests) == ("model" in job)


def test_bare_items_and_visible_archived_layers_are_supported() -> None:
    # Given a server exposing a selected archived layer and an unpaginated item list.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When recognition training uses those visible saved references.
            result = await invoke(
                session,
                "train_collection_recognizer",
                {"collection_id": 5, "job": {"model": 7}},
            )
            # Then native acceptance remains the entire response.
            assert result == {"status": "ok", "model_id": 9, "custom": "retained"}

    with collection_training_fixture(paginated=False) as fixture:
        _ = fixture.items.pop(0)
        fixture.model["job"] = 2
        fixture.responses["GET /api/documents/6/transcriptions/3/"] = {
            "pk": 3,
            "archived": True,
        }
        anyio.run(run, fixture)
    assert all(route != ITEMS + "?page=2" for _, route, _ in fixture.requests)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1


@pytest.mark.parametrize("status", [400, 403, 500])
def test_failed_submission_retains_uncertainty_without_retry(status: int) -> None:
    # Given a server error after the collection has passed all preflight reads.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When the native POST fails.
            result = await session.call_tool(
                "train_collection_recognizer",
                {"collection_id": 5, "job": {"model_name": "new model"}},
            )
            # Then no accepted result or automatic retry hides uncertain effects.
            assert result.is_error
            assert str(status) in result.model_dump_json()
            assert "may" in result.model_dump_json().lower()

    with collection_training_fixture() as fixture:
        fixture.failures["POST " + COLLECTION + "train_recognizer/"] = status
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1
    assert fixture.requests[-1][0] == "POST"


def test_public_running_base_is_allowed_without_overwrite() -> None:
    # Given a readable public model whose existing training must not be overwritten.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When a clone is requested with an explicit false override.
            result = await invoke(
                session,
                "train_collection_recognizer",
                {
                    "collection_id": 5,
                    "job": {"model": 7, "model_name": "clone", "override": False},
                },
            )
            # Then overwrite-only restrictions do not prohibit native cloning.
            assert result == {"status": "ok", "model_id": 9, "custom": "retained"}

    with collection_training_fixture() as fixture:
        fixture.model.update({"rights": "public", "training": True})
        anyio.run(run, fixture)
    assert fixture.requests[-1][0] == "POST"
