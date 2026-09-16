"""Font preferences preserve explicit clearing, omission and native response fields."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.font_fixture import (
    DOCUMENT,
    DOCUMENTS,
    FONT,
    PROJECT,
    PROJECTS,
    FontFixture,
    font_fixture,
    font_session,
)
from tests.font_write_cases import OPERATIONS, Operation, write_case
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("font_id", [None, 3])
def test_font_assignment_and_clear_exact_wire(
    operation: Operation, font_id: int | None
) -> None:
    # Given writable font settings on each native create/update surface.
    case = write_case(operation, {"transcription_font": font_id})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When selecting a font or explicitly clearing the override.
            result = await invoke(session, case.tool, case.arguments)
            # Then the native response and nullable payload survive unchanged.
            assert result == {"saved": case.body}

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    expected: list[tuple[str, str, JsonValue]] = [("OPTIONS", case.route, None)]
    if font_id is not None:
        expected.append(("GET", FONT, None))
    expected.append((case.method, case.route, case.body))
    assert fixture.requests == expected


@pytest.mark.parametrize("operation", OPERATIONS)
def test_omitted_font_retains_original_single_write(operation: Operation) -> None:
    # Given a caller changing another field without requesting a font change.
    changes: dict[str, JsonValue] = (
        {} if operation.endswith("_create") else {"name": "New"}
    )
    case = write_case(operation, changes)

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When executed, then no capability/font query occurs.
            assert await invoke(session, case.tool, case.arguments) == {
                "saved": case.body
            }

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [(case.method, case.route, case.body)]


@pytest.mark.parametrize("resource", ["project", "document"])
@pytest.mark.parametrize("shape", ["effective", "absent"])
def test_record_reads_preserve_native_font_scope(resource: str, shape: str) -> None:
    # Given native font choices or an older response without font fields.
    route = PROJECT if resource == "project" else DOCUMENT
    identity = 1 if resource == "project" else 4

    async def run(fixture: FontFixture) -> None:
        row: dict[str, JsonValue] = {
            "id" if resource == "project" else "pk": identity,
            "name": "Record",
            "native_extra": {"preserved": True},
        }
        if shape == "effective":
            row["transcription_font"] = None if resource == "document" else 3
            if resource == "document":
                row["effective_transcription_font"] = fixture.font
        fixture.responses["GET " + route] = row
        async with font_session(fixture) as session:
            # When read through MCP, then no client fallback is synthesized.
            result = await invoke(
                session, "get_" + resource, {resource + "_id": identity}
            )
            assert result == row

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", route, None)]


@pytest.mark.parametrize("resource", ["project", "document"])
def test_record_lists_preserve_font_metadata(resource: str) -> None:
    # Given populated font fields in the native record catalogue.
    route = PROJECTS if resource == "project" else DOCUMENTS

    async def run(fixture: FontFixture) -> None:
        row: dict[str, JsonValue] = {
            "id" if resource == "project" else "pk": 1,
            "transcription_font": 3,
        }
        if resource == "document":
            row["effective_transcription_font"] = fixture.font
        native: JsonValue = {
            "count": 1,
            "next": None,
            "results": [row],
            "native_extra": "keep",
        }
        fixture.responses["GET " + route] = native
        async with font_session(fixture) as session:
            # When listing existing records, then nested font metrics remain raw.
            assert await invoke(session, "list_" + resource + "s", {}) == native

    with font_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", route, None)]
