"""Page metadata and explicit image replacement across STDIO."""

from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue

from tests.page_fixture import DOC, PAGE, page_fixture, page_session
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    "patch",
    [
        {
            "original_filename": "č-renamed.png",
            "comments": None,
            "max_avg_confidence": -2.5,
        },
        {"name": "", "source": "", "max_avg_confidence": None},
        {"typology": 7},
        {"typology": None},
    ],
)
def test_metadata_patch_preserves_omission_and_null(
    patch: dict[str, JsonValue],
) -> None:
    # Given a page with independently stored image and segmentation.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When supported metadata is patched.
                result = await invoke(
                    session,
                    "update_page",
                    {"document_id": 4, "page_id": 10, "changes": patch},
                )
                # Then only explicitly provided fields are sent to PATCH.
                assert isinstance(result, dict)
                for key, value in patch.items():
                    assert result[key] == value
                assert result["image_file_size"] == 123

        anyio.run(scenario)
    assert fixture.requests[-1] == ("PATCH", PAGE, patch)
    if patch.get("typology") == 7:
        assert ("GET", DOC, None) in fixture.requests


def test_metadata_rejects_unassigned_document_typology() -> None:
    # Given the document assigns only part type7.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When a globally valid but unassigned type is requested.
                result = await session.call_tool(
                    "update_page",
                    {"document_id": 4, "page_id": 10, "changes": {"typology": 99}},
                )
                # Then the global FK cannot bypass document ontology scope.
                assert result.is_error

        anyio.run(scenario)
    assert all(method == "GET" for method, _, _ in fixture.requests)


def test_image_replacement_uploads_exact_file_and_measured_size(tmp_path: Path) -> None:
    # Given a local filename with spaces and existing page geometry.
    image_path = tmp_path / "replacement scan.png"
    content = b"\x89PNG\r\n\x1a\nfixture-image-bytes"
    _ = image_path.write_bytes(content)
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the explicit replacement action uploads that host file.
                result = await invoke(
                    session,
                    "replace_page_image",
                    {"document_id": 4, "page_id": 10, "image_path": str(image_path)},
                )
                # Then existing native geometry fields are returned untouched.
                assert isinstance(result, dict)
                assert result["lines"] == [
                    {"pk": 11, "baseline": [[1, 2], [3, 2]], "mask": None}
                ]
                assert result["regions"] == [
                    {"pk": 21, "locked": True, "box": [[1, 2], [3, 2], [3, 4]]}
                ]

        anyio.run(scenario)
    assert fixture.requests == [("GET", PAGE, None), ("PATCH", PAGE, None)]
    assert len(fixture.uploads) == 1
    payload = fixture.uploads[0]
    assert b'name="image"; filename="replacement scan.png"' in payload
    assert content in payload
    assert (
        b'name="image_file_size"\r\n\r\n' + str(len(content)).encode() + b"\r\n"
        in payload
    )


def test_image_replacement_requires_existing_host_file(tmp_path: Path) -> None:
    # Given a missing file on the MCP server host.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When replacement references that path.
                result = await session.call_tool(
                    "replace_page_image",
                    {
                        "document_id": 4,
                        "page_id": 10,
                        "image_path": str(tmp_path / "missing.png"),
                    },
                )
                # Then no remote read or write is attempted.
                assert result.is_error

        anyio.run(scenario)
    assert fixture.requests == []


def test_image_replacement_preserves_permission_failure_without_retry(
    tmp_path: Path,
) -> None:
    # Given a readable page whose update is denied.
    image_path = tmp_path / "replacement.png"
    _ = image_path.write_bytes(b"fixture")
    with page_fixture() as fixture:
        fixture.failures["PATCH " + PAGE] = 403

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When replacement PATCH encounters permission denial.
                result = await session.call_tool(
                    "replace_page_image",
                    {"document_id": 4, "page_id": 10, "image_path": str(image_path)},
                )
                # Then the error is surfaced without another upload.
                assert result.is_error

        anyio.run(scenario)
    assert fixture.requests == [("GET", PAGE, None), ("PATCH", PAGE, None)]
    assert len(fixture.uploads) == 1
