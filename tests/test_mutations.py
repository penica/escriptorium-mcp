from pathlib import Path

import anyio
import pytest

from tests.mutation_cases import ELEMENT, PAGE, RECORD_CASES, TEXT
from tests.mutation_fixture import Case, api_fixture, exercise


def case_id(case: Case) -> str:
    return case.tool


@pytest.mark.parametrize(
    "case",
    [
        *RECORD_CASES,
        Case(
            "transcribe_pages",
            {
                "document_id": 7,
                "job": {
                    "parts": [11],
                    "model": 2,
                    "transcription": 5,
                },
            },
            "documents/7/transcribe/",
            payload={
                "parts": [11],
                "model": 2,
                "transcription": 5,
            },
        ),
        Case(
            "train_recognition",
            {
                "document_id": 7,
                "job": {
                    "parts": [11, 12],
                    "model_name": "Parish hand",
                    "transcription": 5,
                },
            },
            "documents/7/train/",
            payload={
                "parts": [11, 12],
                "model_name": "Parish hand",
                "transcription": 5,
            },
        ),
        Case(
            "train_segmentation",
            {
                "document_id": 7,
                "job": {
                    "parts": [11, 12],
                    "model": 2,
                    "override": True,
                },
            },
            "documents/7/segtrain/",
            payload={
                "parts": [11, 12],
                "model": 2,
                "override": True,
            },
        ),
        Case(
            "cancel_task",
            {"document_id": 7, "task_id": 44},
            "documents/7/cancel_tasks/",
            payload={"task_report": 44},
        ),
        Case("cancel_page_tasks", PAGE, "documents/7/parts/11/cancel/"),
        Case("cancel_model_training", {"model_id": 2}, "models/2/cancel_training/"),
        Case("delete_document", {"document_id": 7}, "documents/7/", "DELETE"),
        Case("delete_project", {"project_id": 3}, "projects/3/", "DELETE"),
        Case("delete_page", PAGE, "documents/7/parts/11/", "DELETE"),
        Case(
            "delete_transcription",
            {"document_id": 7, "transcription_id": 5},
            "documents/7/transcriptions/5/",
            "DELETE",
        ),
        Case(
            "delete_line_transcription",
            {"target": TEXT},
            "documents/7/parts/11/transcriptions/23/",
            "DELETE",
        ),
        Case(
            "delete_line",
            {"target": ELEMENT},
            "documents/7/parts/11/lines/19/",
            "DELETE",
        ),
        Case(
            "delete_region",
            {"target": ELEMENT},
            "documents/7/parts/11/blocks/19/",
            "DELETE",
        ),
    ],
    ids=case_id,
)
def test_mutation_when_called_through_stdio(case: Case) -> None:
    # Given an isolated API accepting authenticated requests.
    with api_fixture() as fixture:
        # When the actual MCP server and worker execute the mutation.
        # Then the fixture observes the official route, method and payload.
        anyio.run(exercise, fixture, case)


@pytest.mark.parametrize("override", [False, True])
def test_document_import_when_local_file_exists(
    tmp_path: Path,
    *,
    override: bool,
) -> None:
    upload = tmp_path / "transcription.xml"
    _ = upload.write_bytes(b"<alto>fixture</alto>")
    case = Case(
        "import_document_file",
        {
            "document_id": 7,
            "upload": {
                "file_path": str(upload),
                "name": "Imported",
                "override": override,
            },
        },
        "documents/7/imports/",
        multipart=(
            b'name="upload_file"; filename="transcription.xml"',
            b"<alto>fixture</alto>",
            b'name="name"\r\n\r\nImported',
            b'name="override"\r\n\r\n' + str(override).encode(),
        ),
    )
    with api_fixture() as fixture:
        anyio.run(exercise, fixture, case)


@pytest.mark.parametrize(
    "case",
    [
        Case("update_document", {"document_id": 7, "changes": {}}),
        Case("update_page", {**PAGE, "changes": {}}),
        Case("update_line", {"target": ELEMENT, "changes": {}}),
        Case("update_region", {"target": ELEMENT, "changes": {}}),
        Case("update_line_transcription", {"target": TEXT, "changes": {}}),
        Case(
            "create_line",
            {
                "document_id": 7,
                "line": {
                    "document_part": 11,
                    "baseline": [[1, 2]],
                },
            },
        ),
        Case(
            "create_region",
            {
                "document_id": 7,
                "region": {
                    "document_part": 11,
                    "box": [[1, 2], [3, 4]],
                },
            },
        ),
        Case(
            "update_line",
            {
                "target": ELEMENT,
                "changes": {
                    "baseline": [[-1, 2], [3, 4]],
                },
            },
        ),
        Case(
            "update_region",
            {
                "target": ELEMENT,
                "changes": {
                    "box": [[1, 2, 3], [3, 4], [4, 5]],
                },
            },
        ),
        Case(
            "train_segmentation",
            {
                "document_id": 7,
                "job": {
                    "parts": [11],
                    "model_name": "Hand",
                },
            },
        ),
        Case(
            "train_segmentation",
            {
                "document_id": 7,
                "job": {
                    "parts": [11, 11],
                    "model_name": "Hand",
                },
            },
        ),
    ],
    ids=case_id,
)
def test_invalid_input_when_mutation_requested(case: Case) -> None:
    # Given invalid mutation parameters and an observable HTTP fixture.
    with api_fixture() as fixture:
        # When validation runs through the real MCP protocol.
        # Then an MCP error is returned without any network mutation.
        anyio.run(exercise, fixture, case)


def test_page_upload_when_local_file_exists(tmp_path: Path) -> None:
    # Given image bytes with metadata in a local file.
    image = tmp_path / "folio.png"
    _ = image.write_bytes(b"\x89PNG\r\n\x1a\nfixture-image")
    case = Case(
        "upload_page",
        {
            "document_id": 7,
            "image": {
                "image_path": str(image),
                "name": "Folio 1",
                "source": "Parish archive",
            },
        },
        "documents/7/parts/",
        multipart=(
            b'name="image"; filename="folio.png"',
            b"\x89PNG\r\n\x1a\nfixture-image",
            b'name="name"\r\n\r\nFolio 1',
            b'name="source"\r\n\r\nParish archive',
        ),
    )
    with api_fixture() as fixture:
        # When the real worker uploads the page through MCP.
        # Then the API receives the image bytes and metadata as multipart fields.
        anyio.run(exercise, fixture, case)
