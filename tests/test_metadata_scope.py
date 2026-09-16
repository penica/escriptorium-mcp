"""Scope failures prevent metadata writes and remain observable errors."""

import anyio
import pytest

from tests.metadata_fixture import (
    DOC,
    PAGE,
    PAGE_METADATA,
    MetadataFixture,
    metadata_fixture,
    metadata_session,
)


@pytest.mark.parametrize("route", [DOC, PAGE, PAGE_METADATA + "93/"])
@pytest.mark.parametrize("status", [403, 404])
def test_scope_permission_failure_prevents_patch(route: str, status: int) -> None:
    # Given a denied document, page or association detail.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When a page metadata value is changed.
            result = await session.call_tool(
                "update_metadata",
                {
                    "target": {"scope": "page", "document_id": 4, "page_id": 10},
                    "metadata_id": 93,
                    "changes": {"value": "changed"},
                },
            )
            # Then the original permission/not-found status is retained.
            assert result.is_error
            assert str(status) in result.model_dump_json()

    with metadata_fixture() as fixture:
        fixture.failures["GET " + route] = status
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)
    assert fixture.rows[93]["value"] == "page"


@pytest.mark.parametrize("route", [DOC, PAGE, PAGE_METADATA + "93/"])
def test_wrong_returned_identity_prevents_delete(route: str) -> None:
    # Given a server returning an identity outside the requested scope.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When an association is deleted.
            result = await session.call_tool(
                "delete_metadata",
                {
                    "target": {"scope": "page", "document_id": 4, "page_id": 10},
                    "metadata_id": 93,
                },
            )
            # Then the mismatch cannot reach a mutation.
            assert result.is_error

    with metadata_fixture() as fixture:
        fixture.responses["GET " + route] = {"pk": 999, "document": 999}
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)
    assert 93 in fixture.rows


def test_document_row_cannot_be_addressed_as_page_metadata() -> None:
    # Given a document metadata ID absent from the selected page.
    async def run(fixture: MetadataFixture) -> None:
        async with metadata_session(fixture) as session:
            # When its shared key is changed through that page scope.
            result = await session.call_tool(
                "update_shared_metadata_key",
                {
                    "target": {"scope": "page", "document_id": 4, "page_id": 10},
                    "metadata_id": 91,
                    "changes": {"name": "wrong"},
                },
            )
            # Then scoped detail retrieval fails before a shared-key mutation.
            assert result.is_error
            assert "404" in result.model_dump_json()

    with metadata_fixture() as fixture:
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)
    assert fixture.key["name"] == "place"
