"""Metadata reads retain native fields and complete pagination."""

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


@pytest.mark.parametrize("paginated", [False, True])
def test_list_document_metadata_preserves_duplicate_rows(*, paginated: bool) -> None:
    # Given two independent association rows for the same key/value.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When all document metadata is requested.
            result = await invoke(
                session,
                "list_metadata",
                {"target": {"scope": "document", "document_id": 4}},
            )
            # Then native envelopes and duplicate associations survive unchanged.
            expected = [fixture.row(91), fixture.row(92)]
            if paginated:
                assert isinstance(result, dict)
                assert result["results"] == expected
                assert result["count"] == 2
                assert result["next"] is None
            else:
                assert result == expected

    with metadata_fixture(paginated=paginated) as fixture:
        anyio.run(run, fixture)
    assert sum(
        route.startswith(DOCUMENT_METADATA) for _, route, _ in fixture.requests
    ) == (2 if paginated else 1)


@pytest.mark.parametrize("scope", ["document", "page"])
def test_get_metadata_returns_full_scoped_record(scope: str) -> None:
    # Given a metadata row in the selected scope.
    target: dict[str, JsonValue] = {"scope": scope, "document_id": 4}
    if scope == "page":
        target["page_id"] = 10
    identifier = 93 if scope == "page" else 91

    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When one association is retrieved.
            result = await invoke(
                session, "get_metadata", {"target": target, "metadata_id": identifier}
            )
            # Then nested key and custom native fields are preserved.
            assert result == fixture.row(identifier)

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    route = PAGE_METADATA if scope == "page" else DOCUMENT_METADATA
    assert fixture.requests[-1] == ("GET", route + str(identifier) + "/", None)


def test_empty_page_metadata_remains_empty() -> None:
    # Given a page without metadata associations.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When metadata is listed.
            result = await invoke(
                session,
                "list_metadata",
                {"target": {"scope": "page", "document_id": 4, "page_id": 10}},
            )
            # Then an empty page is returned without fabricated defaults.
            assert result == {"count": 0, "next": None, "results": []}

    with metadata_fixture() as fixture:
        fixture.page_ids.clear()
        anyio.run(run, fixture)


def test_shared_key_edit_is_advertised_as_destructive_nonidempotent() -> None:
    # Given the actual public MCP tool catalogue.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When the client discovers shared-key editing.
            result = await session.list_tools()
            tool = next(
                item
                for item in result.tools
                if item.name == "update_shared_metadata_key"
            )
            # Then mutation hints cannot suggest a read or automatically safe retry.
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.destructive_hint is True
            assert tool.annotations.idempotent_hint is False

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
