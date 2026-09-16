"""Source document/page/layer references must prove membership before writes."""

import anyio
import pytest
from pydantic import JsonValue

from tests.collection_fixture import (
    COLLECTION,
    DOC,
    OTHER_DOC,
    CollectionFixture,
    collection_fixture,
    collection_session,
)


@pytest.mark.parametrize(
    ("route", "replacement"),
    [
        (DOC, {"pk": 99}),
        (DOC, {"pk": "4"}),
        (DOC + "parts/11/", {"pk": 12}),
        (DOC + "parts/11/", {}),
        (DOC + "transcriptions/2/", {"pk": 19}),
        (DOC + "transcriptions/2/", {"pk": "2"}),
    ],
)
def test_wrong_or_malformed_source_identity_prevents_creation(
    route: str, replacement: JsonValue
) -> None:
    # Given a source response that cannot establish the requested document context.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When creating collection membership for that page/layer pair.
            result = await session.call_tool(
                "create_collection",
                {
                    "data": {
                        "name": "Invalid",
                        "items": [
                            {"document_id": 4, "page_id": 11, "transcription_id": 2}
                        ],
                    }
                },
            )
            # Then no collection row or links are written.
            assert result.is_error

    with collection_fixture() as fixture:
        fixture.responses[route] = replacement
        anyio.run(run, fixture)
    assert all(r[0] == "GET" for r in fixture.requests)


@pytest.mark.parametrize(
    "tool", ["update_collection", "delete_collection", "get_collection"]
)
def test_wrong_collection_id_is_rejected(tool: str) -> None:
    # Given a detail route returning another collection's native id.
    args: dict[str, JsonValue] = {"collection_id": 7}
    if tool == "update_collection":
        args["changes"] = {"name": "Wrong"}

    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When that detail is used as authority for reading or writing.
            result = await session.call_tool(tool, args)
            # Then the mismatched identity fails before any mutation.
            assert result.is_error

    with collection_fixture() as fixture:
        fixture.responses[COLLECTION] = {"id": 99}
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", COLLECTION, None)]


@pytest.mark.parametrize("archived_visible", [True, False])
def test_archived_layers_are_used_only_when_scoped_endpoint_returns_them(
    *, archived_visible: bool
) -> None:
    # Given an archived layer that is either visible or hidden in its document.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When the layer is used as a UI default without changing saved items.
            result = await session.call_tool(
                "update_collection",
                {"collection_id": 7, "changes": {"default_transcriptions": {"8": 19}}},
            )
            # Then explicit native visibility permits the reference without unarchiving.
            assert result.is_error is not archived_visible

    with collection_fixture() as fixture:
        layer = OTHER_DOC + "transcriptions/19/"
        if archived_visible:
            fixture.responses[layer] = {"pk": 19, "archived": True}
        else:
            fixture.failures[layer] = 404
        original_items = list(fixture.items)
        anyio.run(run, fixture)
    assert fixture.items == original_items
    assert len([r for r in fixture.requests if r[0] == "PATCH"]) == int(
        archived_visible
    )


def test_foreign_page_and_layer_cannot_be_used_under_another_document() -> None:
    # Given valid source IDs from different documents combined into an invalid triple.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When either a foreign page or foreign layer is placed under document4.
            for page, layer in ((12, 2), (11, 19)):
                result = await session.call_tool(
                    "create_collection",
                    {
                        "data": {
                            "name": "Foreign",
                            "items": [
                                {
                                    "document_id": 4,
                                    "page_id": page,
                                    "transcription_id": layer,
                                }
                            ],
                        }
                    },
                )
                # Then the scoped 404 prevents a native collection mutation.
                assert result.is_error

    with collection_fixture() as fixture:
        anyio.run(run, fixture)
    assert all(r[0] == "GET" for r in fixture.requests)
