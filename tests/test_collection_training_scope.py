"""Saved collection members are reauthorized before every training submission."""

import anyio
import pytest
from pydantic import JsonValue

from tests.collection_training_fixture import (
    COLLECTION,
    MODEL,
    CollectionTrainingFixture,
    collection_training_fixture,
    collection_training_session,
)


@pytest.mark.parametrize(
    "route",
    [
        COLLECTION,
        "/api/documents/6/",
        "/api/documents/6/parts/12/",
        "/api/documents/6/transcriptions/3/",
    ],
)
@pytest.mark.parametrize("failure", ["denied", "wrong_id"])
def test_foreign_or_inaccessible_source_prevents_training(
    route: str, failure: str
) -> None:
    # Given a denied or mismatched source, including an item on the second page.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When recognition training revalidates saved collection membership.
            result = await session.call_tool(
                "train_collection_recognizer",
                {"collection_id": 5, "job": {"model_name": "new"}},
            )
            # Then no training job is queued from invalid source evidence.
            assert result.is_error

    with collection_training_fixture() as fixture:
        if failure == "denied":
            fixture.failures["GET " + route] = 403
        else:
            fixture.responses["GET " + route] = {"id": 999, "pk": 999, "document": 999}
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)


@pytest.mark.parametrize(
    "issue",
    [
        "empty",
        "one_segment_page",
        "duplicate_page",
        "missing_layer",
        "foreign_page",
        "hidden_layer",
    ],
)
def test_invalid_membership_prevents_training(issue: str) -> None:
    # Given saved item metadata that cannot form the requested training dataset.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When training validates the complete current membership.
            action = "segmenter" if issue == "one_segment_page" else "recognizer"
            result = await session.call_tool(
                "train_collection_" + action,
                {"collection_id": 5, "job": {"model_name": "new"}},
            )
            # Then empty, incomplete, duplicate or foreign references stop the write.
            assert result.is_error

    with collection_training_fixture() as fixture:
        if issue == "empty":
            fixture.items.clear()
        if issue == "one_segment_page":
            _ = fixture.items.pop()
        if issue == "duplicate_page":
            fixture.items.append(fixture.items[0])
        if issue == "missing_layer":
            fixture.items[1] = {"document_id": 6, "document_part": 12}
        if issue == "foreign_page":
            fixture.items[1] = {
                "document_id": 4,
                "document_part": 12,
                "transcription_layer": 2,
            }
        if issue == "hidden_layer":
            fixture.failures["GET /api/documents/6/transcriptions/3/"] = 404
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)


@pytest.mark.parametrize(
    "change",
    [
        {"pk": 999},
        {"job": "Segment"},
        {"rights": "public"},
        {"training": True},
        {"training": None},
    ],
)
def test_model_guards_apply_even_with_new_name(change: dict[str, JsonValue]) -> None:
    # Given an incompatible identity/job or a model unsafe to overwrite.
    async def run(fixture: CollectionTrainingFixture) -> None:
        async with collection_training_session(fixture) as session:
            # When both model and model_name accompany override=true.
            result = await session.call_tool(
                "train_collection_recognizer",
                {
                    "collection_id": 5,
                    "job": {"model": 7, "model_name": "new name", "override": True},
                },
            )
            # Then a name cannot bypass the model's identity/ownership/state checks.
            assert result.is_error

    with collection_training_fixture() as fixture:
        fixture.model.update(change)
        anyio.run(run, fixture)
    assert ("GET", MODEL, None) in fixture.requests
    assert all(method == "GET" for method, _, _ in fixture.requests)
