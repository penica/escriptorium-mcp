"""Import scope guards and group-filtered reporting through real STDIO."""

from pathlib import Path

import anyio
import pytest

from tests.import_fixture import (
    DOC,
    GROUPS,
    LAYER,
    METHOD,
    ImportFixture,
    import_fixture,
    import_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    "failure", ["document", "document_pk", "layer404", "layer_pk", "layer_name"]
)
def test_scope_failure_prevents_import(failure: str) -> None:
    # Given missing, foreign or unrepresentable target metadata.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When an existing layer name is requested as a METS prefix.
            result = await session.call_tool(
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "mets_url",
                        "url": "https://example.org/book.xml",
                        "prefix_transcription_id": 2,
                    },
                },
            )
            # Then validation fails before any write.
            assert result.is_error

    with import_fixture() as fixture:
        if failure == "document":
            fixture.failures[DOC] = 403
        if failure == "document_pk":
            fixture.document["pk"] = 999
        if failure == "layer404":
            fixture.failures[LAYER] = 404
        if failure == "layer_pk":
            fixture.layer["pk"] = 999
        if failure == "layer_name":
            fixture.layer["name"] = "x" * 257
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)


def test_visible_archived_layer_is_accepted_without_unarchiving() -> None:
    # Given a deployment exposing an archived layer supported by native imports.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the visible archived layer is used as a prefix.
            result = await invoke(
                session,
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "mets_url",
                        "url": "https://example.org/book.xml",
                        "prefix_transcription_id": 2,
                    },
                },
            )
            # Then native acceptance does not require altering the layer.
            assert result == {"status": "ok"}

    with import_fixture() as fixture:
        fixture.layer["archived"] = True
        anyio.run(run, fixture)
    assert fixture.layer["archived"] is True
    assert all(method in {"GET", "POST"} for method, _, _ in fixture.requests)


@pytest.mark.parametrize("kind", ["pdf_file", "xml_file", "mets_file"])
@pytest.mark.parametrize("file_case", ["missing", "wrong_suffix"])
def test_missing_or_mismatched_file_never_posts(
    tmp_path: Path, kind: str, file_case: str
) -> None:
    # Given an absent file or incompatible extension on the MCP host.
    upload = tmp_path / ("bad.txt" if file_case == "wrong_suffix" else "missing.xml")
    if file_case == "wrong_suffix":
        _ = upload.write_text("fixture")

    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the file source is submitted.
            result = await session.call_tool(
                "submit_document_import",
                {"document_id": 4, "source": {"kind": kind, "file_path": str(upload)}},
            )
            # Then it cannot become an upstream import.
            assert result.is_error

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.uploads
    assert all(method == "GET" for method, _, _ in fixture.requests)


def test_import_status_scopes_group_and_method() -> None:
    # Given a group containing a finished import report with warning text.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When one import group is monitored.
            result = await invoke(
                session, "get_import_status", {"document_id": 4, "group_id": 2}
            )
            # Then the full report and its warning survive summary construction.
            assert isinstance(result, dict)
            assert "skipped file" in str(result)
            assert "processed" not in result
            assert result["total"] == 1
            assert result["all_finished"] is True

    with import_fixture() as fixture:
        fixture.reports.append(
            {
                "pk": 8,
                "document": 4,
                "workflow_state": 3,
                "method": METHOD,
                "messages": "skipped file",
                "group": 2,
            }
        )
        fixture.reports.append(
            {"pk": 9, "workflow_state": 2, "method": "core.tasks.train"}
        )
        anyio.run(run, fixture)
    assert ("GET", GROUPS + "2/", None) in fixture.requests
    task_routes = [
        route
        for method, route, _ in fixture.requests
        if method == "GET" and route.startswith("/api/tasks/")
    ]
    assert len(task_routes) == 1
    assert "group=2" in task_routes[0]
    assert "document=4" in task_routes[0]
    assert "method=" not in task_routes[0]


def test_cancel_keeps_latest_import_native_action() -> None:
    # Given an existing document whose latest import is cancelable.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When cancellation is requested without an invented import ID.
            result = await invoke(session, "cancel_document_import", {"document_id": 4})
            # Then the native cancellation result is returned unchanged.
            assert result == {"status": "canceled"}

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", DOC + "cancel_import/", {})]


def test_import_status_stops_when_group_is_inaccessible() -> None:
    # Given a group that is not visible within the selected document.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the scoped group is monitored.
            result = await session.call_tool(
                "get_import_status", {"document_id": 4, "group_id": 2}
            )
            # Then its permission failure does not become an empty success.
            assert result.is_error
            assert "403" in result.model_dump_json()

    with import_fixture() as fixture:
        fixture.failures[GROUPS + "2/"] = 403
        anyio.run(run, fixture)
    assert all(not route.startswith("/api/tasks/") for _, route, _ in fixture.requests)
