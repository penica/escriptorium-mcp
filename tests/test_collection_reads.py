"""Collection reads retain raw metadata, full membership and native errors."""

import anyio
import pytest

from tests.collection_fixture import (
    COLLECTION,
    COLLECTIONS,
    ITEMS,
    CollectionFixture,
    collection_fixture,
    collection_session,
)
from tests.transcription_fixture import invoke


def test_raw_collection_metadata_and_membership_are_preserved() -> None:
    # Given native id metadata and cross-document membership with unknown fields.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When all three public read surfaces are called.
            listed = await invoke(session, "list_collections", {})
            detail = await invoke(session, "get_collection", {"collection_id": 7})
            items = await invoke(session, "list_collection_items", {"collection_id": 7})
            # Then native metadata and source identity fields survive unchanged.
            assert listed == {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [fixture.collection],
            }
            assert detail == fixture.collection
            assert items == {"count": 2, "next": None, "results": fixture.items}

    with collection_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", COLLECTIONS, None),
        ("GET", COLLECTION, None),
        ("GET", COLLECTION, None),
        ("GET", ITEMS, None),
    ]


def test_bare_and_empty_collections_are_not_rewrapped() -> None:
    # Given servers returning a bare collection and an empty member list.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When native list shapes are read.
            assert await invoke(session, "list_collections", {}) == [fixture.collection]
            assert (
                await invoke(session, "list_collection_items", {"collection_id": 7})
                == []
            )

    with collection_fixture() as fixture:
        fixture.responses[COLLECTIONS] = [fixture.collection]
        fixture.responses[ITEMS] = []
        anyio.run(run, fixture)


@pytest.mark.parametrize("status", [403, 404])
def test_inaccessible_collection_is_not_empty_success(status: int) -> None:
    # Given missing or unreadable collection metadata.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When a client asks for detail or items.
            for tool in ("get_collection", "list_collection_items"):
                result = await session.call_tool(tool, {"collection_id": 7})
                # Then the native access error remains an error, never an empty list.
                assert result.is_error

    with collection_fixture() as fixture:
        fixture.failures[COLLECTION] = status
        anyio.run(run, fixture)
    assert all(r[1] == COLLECTION for r in fixture.requests)
