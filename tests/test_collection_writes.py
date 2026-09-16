"""Collection membership writes preserve replacement and partial-effect semantics."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.collection_fixture import (
    COLLECTION,
    COLLECTIONS,
    DOC,
    OTHER_DOC,
    CollectionFixture,
    collection_fixture,
    collection_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_collection_create_omits_optional_defaults() -> None:
    # Given a name-only request for a new native collection.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When the collection is created without default-layer or membership data.
            result = await invoke(
                session, "create_collection", {"data": {"name": "New"}}
            )
            # Then the raw owned collection metadata survives without aliases.
            assert result == fixture.collection

    with collection_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", COLLECTIONS, {"name": "New"})]


def test_cross_document_membership_maps_only_native_fields() -> None:
    # Given two source books and a separate default-layer map.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When both document/page/layer triples are submitted.
            result = await invoke(
                session,
                "create_collection",
                {
                    "data": {
                        "name": "Combined",
                        "default_transcriptions": {"4": 2, "8": 19},
                        "items": [
                            {"document_id": 4, "page_id": 11, "transcription_id": 2},
                            {"document_id": 8, "page_id": 12, "transcription_id": 19},
                        ],
                    }
                },
            )
            # Then collection metadata remains native and caller context is not stored.
            assert result == fixture.collection

    with collection_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", DOC, None),
        ("GET", OTHER_DOC, None),
        ("GET", DOC + "parts/11/", None),
        ("GET", OTHER_DOC + "parts/12/", None),
        ("GET", DOC + "transcriptions/2/", None),
        ("GET", OTHER_DOC + "transcriptions/19/", None),
        (
            "POST",
            COLLECTIONS,
            {
                "name": "Combined",
                "default_transcriptions": {"4": 2, "8": 19},
                "items_to_save": [
                    {"document_part": 11, "transcription_layer": 2},
                    {"document_part": 12, "transcription_layer": 19},
                ],
            },
        ),
    ]


def test_patch_omission_defaults_and_membership_clears_are_independent() -> None:
    # Given saved links and a default layer map that have separate native meanings.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            original_items = list(fixture.items)
            # When the default map is cleared without supplying membership.
            _ = await invoke(
                session,
                "update_collection",
                {
                    "collection_id": 7,
                    "changes": {"name": "N" * 512, "default_transcriptions": {}},
                },
            )
            # Then existing links survive; an explicit items=[] clears only links.
            assert fixture.items == original_items
            _ = await invoke(
                session,
                "update_collection",
                {
                    "collection_id": 7,
                    "changes": {"items": []},
                },
            )
            assert fixture.items == []
            assert fixture.collection["default_transcriptions"] == {}

    with collection_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("GET", COLLECTION, None),
        ("PATCH", COLLECTION, {"name": "N" * 512, "default_transcriptions": {}}),
        ("GET", COLLECTION, None),
        ("PATCH", COLLECTION, {"items_to_save": []}),
    ]


def test_complete_membership_replacement_removes_only_links() -> None:
    # Given two collection members and independent source records.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When an explicit full replacement keeps only one source page.
            _ = await invoke(
                session,
                "update_collection",
                {
                    "collection_id": 7,
                    "changes": {
                        "items": [
                            {"document_id": 8, "page_id": 12, "transcription_id": 19},
                        ]
                    },
                },
            )
            # Then the replacement changes membership while source content remains.
            assert fixture.items == [{"document_part": 12, "transcription_layer": 19}]
            assert DOC + "parts/11/" in fixture.source_records
            assert fixture.collection["default_transcriptions"] == {"4": 2}

    with collection_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r for r in fixture.requests if r[0] == "PATCH"] == [
        (
            "PATCH",
            COLLECTION,
            {"items_to_save": [{"document_part": 12, "transcription_layer": 19}]},
        ),
    ]


def test_delete_bodyless_success_removes_collection_without_source_queries() -> None:
    # Given a collection with links into two source documents.
    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When deleting the collection, not any source document.
            result = await invoke(session, "delete_collection", {"collection_id": 7})
            # Then the native bodyless success is represented without invented erasure.
            assert result == {"status": "success", "http_status": 204}

    with collection_fixture() as fixture:
        original_sources = dict(fixture.source_records)
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", COLLECTION, None), ("DELETE", COLLECTION, {})]
    assert fixture.source_records == original_sources
    assert not fixture.collection
    assert not fixture.items


@pytest.mark.parametrize("tool", ["create_collection", "update_collection"])
@pytest.mark.parametrize("failure", ["disconnect", "server_error"])
def test_uncertain_write_warns_of_partial_effects_without_retry(
    tool: str, failure: str
) -> None:
    # Given an uncertain native write: lost response or server-side failure.
    args: dict[str, JsonValue] = (
        {"data": {"name": "Saved"}}
        if tool == "create_collection"
        else {"collection_id": 7, "changes": {"name": "Saved"}}
    )

    async def run(fixture: CollectionFixture) -> None:
        async with collection_session(fixture) as session:
            # When the write's response is lost.
            result = await session.call_tool(tool, args)
            # Then a possible partial write is reported with no automatic resubmission.
            assert result.is_error
            assert "may already" in result.model_dump_json().lower()
            assert "no automatic retry" in result.model_dump_json().lower()

    with collection_fixture() as fixture:
        endpoint = (
            "POST " + COLLECTIONS
            if tool == "create_collection"
            else "PATCH " + COLLECTION
        )
        if failure == "disconnect":
            fixture.disconnect.add(endpoint)
        else:
            fixture.failures[endpoint] = 500
        anyio.run(run, fixture)
    assert len([r for r in fixture.requests if r[0] != "GET"]) == 1
    if failure == "disconnect":
        assert fixture.collection["name"] == "Saved"
