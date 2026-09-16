"""Modern import requests cross the real MCP and upstream HTTP boundaries."""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from tests.import_fixture import (
    IMPORT,
    LAYER,
    ImportFixture,
    import_fixture,
    import_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_iiif_submission_uses_modern_endpoint() -> None:
    # Given an isolated document and an external manifest URL.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the explicit IIIF import is submitted.
            result = await invoke(
                session,
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "iiif_url",
                        "url": "https://example.org/manifest.json",
                    },
                },
            )
            # Then the native accepted response is retained without invented IDs.
            assert result == {"status": "ok"}

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        IMPORT,
        {"mode": "iiif", "iiif_uri": "https://example.org/manifest.json"},
    )


@pytest.mark.parametrize(
    ("kind", "suffix", "expected"),
    [
        ("pdf_file", ".pdf", {"mode": "pdf"}),
        ("xml_file", ".xml", {"mode": "xml", "override": "False"}),
        ("xml_file", ".zip", {"mode": "xml", "override": "False"}),
        (
            "mets_file",
            ".xml",
            {"mode": "mets", "mets_type": "local", "override": "False"},
        ),
        (
            "mets_file",
            ".zip",
            {"mode": "mets", "mets_type": "local", "override": "False"},
        ),
    ],
)
def test_local_sources_use_upload_file_multipart(
    tmp_path: Path, kind: str, suffix: str, expected: dict[str, str]
) -> None:
    # Given a file on the MCP host, including a path with spaces.
    upload = tmp_path / ("source document" + suffix)
    _ = upload.write_bytes(b"fixture file bytes")

    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the local mode is submitted once.
            result = await invoke(
                session,
                "submit_document_import",
                {"document_id": 4, "source": {"kind": kind, "file_path": str(upload)}},
            )
            # Then the upstream accepted response survives unchanged.
            assert result == {"status": "ok"}

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r for r in fixture.requests if r[0] == "POST"] == [("POST", IMPORT, None)]
    assert len(fixture.uploads) == 1
    raw = fixture.uploads[0]
    assert b'name="upload_file"; filename="source document' in raw
    assert b"fixture file bytes" in raw
    for field, value in expected.items():
        assert f'name="{field}"\r\n\r\n{value}\r\n'.encode() in raw
    assert b'name="transcription"' not in raw
    assert b'name="iiif_uri"' not in raw


@pytest.mark.parametrize("use_id", [False, True])
def test_mets_url_uses_name_prefix_or_native_transcription_id(*, use_id: bool) -> None:
    # Given a remote METS descriptor and a prefix selection.
    source: dict[str, JsonValue] = {
        "kind": "mets_url",
        "url": "https://example.org/book.xml",
        "override": True,
    }
    source.update({"prefix_transcription_id": 2} if use_id else {"name": "OCR"})

    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the descriptor is submitted for server-side fetching.
            result = await invoke(
                session, "submit_document_import", {"document_id": 4, "source": source}
            )
            # Then no invented import/job identity is returned.
            assert result == {"status": "ok"}

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    expected: dict[str, JsonValue] = {
        "mode": "mets",
        "mets_type": "url",
        "mets_uri": "https://example.org/book.xml",
        "override": True,
    }
    expected.update({"transcription": 2} if use_id else {"name": "OCR"})
    assert fixture.requests[-1] == ("POST", IMPORT, expected)
    assert (
        ("GET", LAYER, None) in fixture.requests
        if use_id
        else all(r[1] != LAYER for r in fixture.requests)
    )
    assert not fixture.uploads


def test_xml_existing_layer_sends_scoped_id(tmp_path: Path) -> None:
    # Given an existing document-owned text layer and local XML.
    upload = tmp_path / "page.xml"
    _ = upload.write_text("<Page/>")

    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the layer is selected by ID.
            result = await invoke(
                session,
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "xml_file",
                        "file_path": str(upload),
                        "transcription_id": 2,
                        "override": True,
                    },
                },
            )
            # Then submission preserves native acceptance.
            assert result == {"status": "ok"}

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert ("GET", LAYER, None) in fixture.requests
    assert b'name="transcription"\r\n\r\n2\r\n' in fixture.uploads[0]
    assert b'name="name"' not in fixture.uploads[0]
    assert b'name="override"\r\n\r\nTrue\r\n' in fixture.uploads[0]


def test_legacy_file_import_retains_plural_endpoint(tmp_path: Path) -> None:
    # Given an existing client's legacy upload arguments.
    upload = tmp_path / "legacy.xml"
    _ = upload.write_text("<Page/>")

    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the legacy tool is invoked unchanged.
            result = await invoke(
                session,
                "import_document_file",
                {
                    "document_id": 4,
                    "upload": {
                        "file_path": str(upload),
                        "name": "legacy",
                        "override": False,
                    },
                },
            )
            # Then its original native response and route remain available.
            assert result == {"status": "ok"}

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r for r in fixture.requests if r[0] == "POST"] == [
        ("POST", "/api/documents/4/imports/", None)
    ]
    assert b'name="name"\r\n\r\nlegacy\r\n' in fixture.uploads[0]


def test_import_schema_marks_mutation_destructive_and_nonidempotent() -> None:
    # Given the published tool list on a real STDIO connection.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the client discovers import annotations.
            result = await session.list_tools()
            tool = next(
                tool for tool in result.tools if tool.name == "submit_document_import"
            )
            # Then annotations warn of overwrites and unsafe retries.
            assert tool.annotations is not None
            assert tool.annotations.destructive_hint is True
            assert tool.annotations.idempotent_hint is False
            assert tool.annotations.read_only_hint is False

    with import_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
