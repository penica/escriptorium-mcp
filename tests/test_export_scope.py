"""Export scope and active-layer checks run before the sole job submission."""

import anyio
import pytest
from pydantic import JsonValue

from tests.export_submission_fixture import (
    DOC,
    LAYER,
    PARTS,
    ExportFixture,
    export_fixture,
    export_session,
)


@pytest.mark.parametrize(
    ("route", "response"),
    [
        (DOC, {"pk": 99, "valid_block_types": []}),
        (DOC, {"valid_block_types": []}),
        (LAYER, {"pk": 99, "archived": False}),
        (LAYER, {"pk": 2, "archived": True}),
        (LAYER, {"pk": 2}),
        (LAYER, {"pk": "2", "archived": False}),
        (PARTS, {"results": [{"pk": 99}], "next": None}),
        (PARTS, {"results": [{"pk": "11"}], "next": None}),
        (DOC, {"pk": 4, "valid_block_types": [{"pk": 99, "name": "Foreign"}]}),
        (DOC, {"pk": 4, "valid_block_types": [{"pk": "3", "name": "Malformed"}]}),
    ],
)
def test_scope_mismatch_or_malformed_metadata_blocks_export(
    route: str,
    response: JsonValue,
) -> None:
    # Given upstream metadata that does not prove the supplied document scope.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When an archive requests selected pages, region types and all layers.
            result = await session.call_tool(
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {
                        "transcription": 2,
                        "file_format": "json",
                        "all_transcriptions": True,
                        "parts": [11],
                        "region_types": [3],
                    },
                },
            )
            # Then all-layers mode never bypasses the active anchor layer check.
            assert result.is_error

    with export_fixture() as fixture:
        fixture.responses[route] = response
        anyio.run(run, fixture)
    assert not [r for r in fixture.requests if r[0] == "POST"]


@pytest.mark.parametrize("route", [DOC, LAYER, PARTS])
def test_scope_access_failure_does_not_submit(route: str) -> None:
    # Given an inaccessible document, layer or selected-page catalogue.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When preflight receives a permission error.
            result = await session.call_tool(
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {"transcription": 2, "parts": [11]},
                },
            )
            # Then a native export is never sent.
            assert result.is_error

    with export_fixture() as fixture:
        fixture.failures[route] = 403
        anyio.run(run, fixture)
    assert not [r for r in fixture.requests if r[0] == "POST"]


def test_selected_page_beyond_first_catalogue_page_is_allowed() -> None:
    # Given a selected page that appears only on the second scoped catalogue page.
    async def run(fixture: ExportFixture) -> None:
        async with export_session(fixture) as session:
            # When the page scope is checked through native pagination.
            result = await session.call_tool(
                "request_server_export",
                {
                    "document_id": 4,
                    "export": {"transcription": 2, "parts": [12], "region_types": [3]},
                },
            )
            # Then all document-owned rows participate in the membership check.
            assert not result.is_error, result.content

    with export_fixture() as fixture:
        fixture.responses[PARTS] = {
            "count": 2,
            "results": [{"pk": 11}],
            "next": PARTS + "?page=2",
        }
        fixture.responses[PARTS + "?page=2"] = {
            "count": 2,
            "results": [{"pk": 12}],
            "next": None,
        }
        anyio.run(run, fixture)
    assert ("GET", PARTS + "?page=2", None) in fixture.requests
    assert len([r for r in fixture.requests if r[0] == "POST"]) == 1
