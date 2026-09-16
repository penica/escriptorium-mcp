"""Typed public-call cases shared by font assignment boundary tests."""

from dataclasses import dataclass
from typing import Literal, assert_never

from pydantic import JsonValue

from tests.font_fixture import DOCUMENT, DOCUMENTS, PROJECT, PROJECTS

Operation = Literal[
    "project_create", "project_update", "document_create", "document_update"
]
OPERATIONS: tuple[Operation, ...] = (
    "project_create",
    "project_update",
    "document_create",
    "document_update",
)


@dataclass(frozen=True, slots=True)
class WriteCase:
    """Immutable operation description carrying the exact expected native body."""

    tool: str
    method: str
    route: str
    arguments: dict[str, JsonValue]
    body: dict[str, JsonValue]


def write_case(operation: Operation, changes: dict[str, JsonValue]) -> WriteCase:
    match operation:
        case "project_create":
            return WriteCase(
                "create_project",
                "POST",
                PROJECTS,
                {"name": "New", "settings": changes},
                {"name": "New", **changes},
            )
        case "project_update":
            return WriteCase(
                "update_project",
                "PATCH",
                PROJECT,
                {"project_id": 1, "changes": changes},
                changes,
            )
        case "document_create":
            body: dict[str, JsonValue] = {
                "name": "New",
                "project": "old",
                "main_script": "Latin",
                **changes,
            }
            return WriteCase("create_document", "POST", DOCUMENTS, {"data": body}, body)
        case "document_update":
            return WriteCase(
                "update_document",
                "PATCH",
                DOCUMENT,
                {"document_id": 4, "changes": changes},
                changes,
            )
        case _:
            assert_never(operation)
