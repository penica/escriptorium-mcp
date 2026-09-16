from typing import Final

from pydantic import JsonValue

from tests.mutation_fixture import Case

PAGE: Final[dict[str, JsonValue]] = {"document_id": 7, "page_id": 11}
ELEMENT: Final[dict[str, JsonValue]] = {**PAGE, "element_id": 19}
TEXT: Final[dict[str, JsonValue]] = {**PAGE, "line_transcription_id": 23}
BASELINE: Final[JsonValue] = [[1, 2], [100, 2]]
POLYGON: Final[JsonValue] = [[1, 1], [100, 1], [100, 20], [1, 20]]


RECORD_CASES: Final = (
    Case(
        "create_document",
        {
            "data": {
                "name": "Parish register",
                "project": "archive",
                "main_script": "Latin",
            }
        },
        "documents/",
        payload={
            "name": "Parish register",
            "project": "archive",
            "main_script": "Latin",
        },
    ),
    Case(
        "update_document",
        {
            "document_id": 7,
            "changes": {
                "name": "New title",
                "project": "other",
                "read_direction": "rtl",
            },
        },
        "documents/7/",
        "PATCH",
        {
            "name": "New title",
            "project": "other",
            "read_direction": "rtl",
        },
    ),
    Case(
        "rename_project",
        {"project_id": 3, "name": "New archive"},
        "projects/3/",
        "PATCH",
        {"name": "New archive"},
    ),
    Case(
        "update_page",
        {**PAGE, "changes": {"name": "Folio 1", "typology": None}},
        "documents/7/parts/11/",
        "PATCH",
        {"name": "Folio 1", "typology": None},
    ),
    Case(
        "create_line_transcription",
        {
            **PAGE,
            "text": {
                "line": 19,
                "transcription": 5,
                "content": "Jožef Penič",
            },
        },
        "documents/7/parts/11/transcriptions/",
        payload={
            "line": 19,
            "transcription": 5,
            "content": "Jožef Penič",
        },
    ),
    Case(
        "update_line_transcription",
        {"target": TEXT, "changes": {"content": ""}},
        "documents/7/parts/11/transcriptions/23/",
        "PATCH",
        {"content": ""},
    ),
    Case(
        "rename_transcription",
        {"document_id": 7, "transcription_id": 5, "changes": {"name": "Verified"}},
        "documents/7/transcriptions/5/",
        "PATCH",
        {"name": "Verified"},
    ),
    Case(
        "create_line",
        {
            "document_id": 7,
            "line": {
                "document_part": 11,
                "baseline": BASELINE,
                "mask": POLYGON,
                "region": 8,
            },
        },
        "documents/7/parts/11/lines/",
        payload={
            "document_part": 11,
            "baseline": BASELINE,
            "mask": POLYGON,
            "region": 8,
        },
        preflight=(
            ("GET", "/api/documents/7/parts/11/"),
            ("GET", "/api/documents/7/parts/11/blocks/"),
        ),
    ),
    Case(
        "update_line",
        {
            "target": ELEMENT,
            "changes": {
                "baseline": BASELINE,
                "region": None,
            },
        },
        "documents/7/parts/11/lines/19/",
        "PATCH",
        {
            "baseline": BASELINE,
            "region": None,
        },
        preflight=(
            ("GET", "/api/documents/7/parts/11/"),
            ("GET", "/api/documents/7/parts/11/lines/19/"),
        ),
    ),
    Case(
        "create_region",
        {
            "document_id": 7,
            "region": {
                "document_part": 11,
                "box": POLYGON,
                "typology": 4,
            },
        },
        "documents/7/parts/11/blocks/",
        payload={
            "document_part": 11,
            "box": POLYGON,
            "typology": 4,
        },
        preflight=(("GET", "/api/documents/7/parts/11/"), ("GET", "/api/documents/7/")),
    ),
    Case(
        "update_region",
        {"target": ELEMENT, "changes": {"box": POLYGON}},
        "documents/7/parts/11/blocks/19/",
        "PATCH",
        {"box": POLYGON},
        preflight=(
            ("GET", "/api/documents/7/parts/11/"),
            ("GET", "/api/documents/7/parts/11/blocks/19/"),
        ),
    ),
    Case(
        "move_page",
        {**PAGE, "position": {"index": 0}},
        "documents/7/parts/11/move/",
        payload={"index": 0},
    ),
    Case(
        "reorder_lines",
        {
            **PAGE,
            "order": {
                "lines": [
                    {"pk": 20, "order": 0},
                    {"pk": 19, "order": 1},
                ]
            },
        },
        "documents/7/parts/11/lines/move/",
        payload={
            "lines": [
                {"pk": 20, "order": 0},
                {"pk": 19, "order": 1},
            ]
        },
        preflight=(
            ("GET", "/api/documents/7/parts/11/"),
            ("GET", "/api/documents/7/parts/11/lines/"),
        ),
    ),
    Case(
        "request_server_export",
        {
            "document_id": 7,
            "export": {
                "transcription": 5,
                "file_format": "pagexml",
                "parts": [11],
                "region_types": ["Undefined", "Orphan", 1],
            },
        },
        "documents/7/export/",
        payload={
            "transcription": 5,
            "file_format": "pagexml",
            "parts": [11],
            "region_types": ["Undefined", "Orphan", 1],
            "include_characters": False,
        },
    ),
    Case(
        "segment_pages",
        {
            "document_id": 7,
            "job": {
                "parts": [11],
                "model": 2,
                "steps": "lines",
                "override": True,
                "text_direction": "horizontal-rl",
            },
        },
        "documents/7/segment/",
        payload={
            "parts": [11],
            "model": 2,
            "steps": "lines",
            "override": True,
            "text_direction": "horizontal-rl",
        },
    ),
)
