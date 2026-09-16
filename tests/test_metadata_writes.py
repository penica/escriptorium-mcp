"""Metadata association changes remain separate from shared-key mutations."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.metadata_fixture import (
    DOCUMENT_METADATA,
    PAGE_METADATA,
    MetadataFixture,
    metadata_fixture,
    metadata_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize("scope", ["document", "page"])
@pytest.mark.parametrize("cidoc", ["omitted", "null", "blank"])
def test_create_metadata_preserves_cidoc_presence(scope: str, cidoc: str) -> None:
    # Given a key and a value, including an existing duplicate association.
    target: dict[str, JsonValue] = {"scope": scope, "document_id": 4}
    if scope == "page":
        target["page_id"] = 10
    key: dict[str, JsonValue] = {"name": "place"}
    if cidoc != "omitted":
        key["cidoc_id"] = None if cidoc == "null" else ""
    data: dict[str, JsonValue] = {"key": key, "value": "same"}

    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When an association is created.
            result = await invoke(
                session, "create_metadata", {"target": target, "data": data}
            )
            # Then it receives a new identity instead of silently updating a match.
            assert result == {"pk": 94, **data}

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    route = PAGE_METADATA if scope == "page" else DOCUMENT_METADATA
    assert fixture.requests[-1] == ("POST", route, data)
    assert fixture.rows[91]["value"] == "same"
    assert 94 in fixture.rows


@pytest.mark.parametrize("scope", ["document", "page"])
def test_value_update_does_not_change_global_key(scope: str) -> None:
    # Given two associations referencing the same global definition.
    target: dict[str, JsonValue] = {"scope": scope, "document_id": 4}
    if scope == "page":
        target["page_id"] = 10
    identifier = 93 if scope == "page" else 91

    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When one value is changed.
            result = await invoke(
                session,
                "update_metadata",
                {
                    "target": target,
                    "metadata_id": identifier,
                    "changes": {"value": "new"},
                },
            )
            # Then only that association's value changes.
            assert isinstance(result, dict)
            assert result["value"] == "new"
            assert result["key"] == {"name": "place", "cidoc_id": "P7"}

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1][2] == {"value": "new"}
    assert fixture.rows[92]["value"] == "same"
    assert fixture.key == {"name": "place", "cidoc_id": "P7"}


def test_shared_key_update_changes_all_references_without_value_payload() -> None:
    # Given document and page rows pointing to one global metadata definition.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When the explicit shared-key operation renames and clears CIDOC.
            result = await invoke(
                session,
                "update_shared_metadata_key",
                {
                    "target": {"scope": "document", "document_id": 4},
                    "metadata_id": 91,
                    "changes": {"name": "location", "cidoc_id": None},
                },
            )
            # Then the returned row exposes the edited global key.
            assert isinstance(result, dict)
            assert result["key"] == {"name": "location", "cidoc_id": None}

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "PATCH",
        DOCUMENT_METADATA + "91/",
        {"key": {"name": "location", "cidoc_id": None}},
    )
    page_row = fixture.row(93)
    assert isinstance(page_row, dict)
    assert page_row["key"] == {"name": "location", "cidoc_id": None}
    assert fixture.rows[91]["value"] == "same"
    assert fixture.rows[93]["value"] == "page"


@pytest.mark.parametrize("scope", ["document", "page"])
def test_delete_removes_only_association(scope: str) -> None:
    # Given independent metadata rows sharing a global key.
    target: dict[str, JsonValue] = {"scope": scope, "document_id": 4}
    if scope == "page":
        target["page_id"] = 10
    identifier = 93 if scope == "page" else 91

    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When one association is deleted.
            result = await invoke(
                session,
                "delete_metadata",
                {"target": target, "metadata_id": identifier},
            )
            # Then the native empty deletion response is represented honestly.
            assert result == {"status": "success", "http_status": 204}

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    assert identifier not in fixture.rows
    assert 92 in fixture.rows
    assert fixture.key == {"name": "place", "cidoc_id": "P7"}
    assert sum(method == "DELETE" for method, _, _ in fixture.requests) == 1


@pytest.mark.parametrize("status", [400, 500])
def test_shared_key_failure_does_not_retry_or_change_value(status: int) -> None:
    # Given an upstream conflict or save failure while editing a shared key.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When the global name change fails.
            result = await session.call_tool(
                "update_shared_metadata_key",
                {
                    "target": {"scope": "document", "document_id": 4},
                    "metadata_id": 91,
                    "changes": {"name": "taken"},
                },
            )
            # Then it remains an error with no implicit retry.
            assert result.is_error
            assert str(status) in result.model_dump_json()

    with metadata_fixture() as fixture:
        fixture.failures["PATCH " + DOCUMENT_METADATA + "91/"] = status
        anyio.run(run, fixture)
    assert sum(method == "PATCH" for method, _, _ in fixture.requests) == 1
    assert fixture.rows[91]["value"] == "same"
