"""Image and ordering actions preserve native contracts and never retry writes."""

import anyio
import pytest
from pydantic import JsonValue

from tests.page_fixture import DOC, PAGE, page_fixture, page_session
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    ("tool", "payload", "route", "body"),
    [
        ("rotate_page", {"angle": 90}, "rotate/", {"angle": 90}),
        ("rotate_page", {"angle": -359}, "rotate/", {"angle": -359}),
        (
            "crop_page",
            {"box": {"x1": 10, "y1": 5, "x2": 100, "y2": 80}},
            "crop/",
            {"x1": 10, "y1": 5, "x2": 100, "y2": 80},
        ),
    ],
)
def test_image_actions_return_native_synchronous_status(
    tool: str, payload: dict[str, JsonValue], route: str, body: JsonValue
) -> None:
    # Given a page with known current dimensions.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When an image action is submitted.
                result = await invoke(
                    session, tool, {"document_id": 4, "page_id": 10, **payload}
                )
                # Then the native completion has no invented task ID.
                assert result == {"status": "done"}

        anyio.run(scenario)
    assert fixture.requests == [("GET", PAGE, None), ("POST", PAGE + route, body)]


@pytest.mark.parametrize(
    ("tool", "payload", "route"),
    [
        ("rotate_page", {"angle": 90}, "rotate/"),
        ("crop_page", {"box": {"x1": 0, "y1": 0, "x2": 50, "y2": 40}}, "crop/"),
    ],
)
def test_partial_image_failure_is_not_retried(
    tool: str, payload: dict[str, JsonValue], route: str
) -> None:
    # Given an upstream action that changes the image before a later save fails.
    with page_fixture() as fixture:
        fixture.failures[PAGE + route] = 500

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the non-atomic action fails.
                result = await session.call_tool(
                    tool, {"document_id": 4, "page_id": 10, **payload}
                )
                # Then MCP reports failure and leaves retries to the caller.
                assert result.is_error

        anyio.run(scenario)
    assert len([request for request in fixture.requests if request[0] == "POST"]) == 1
    row = fixture.rows[0]
    assert isinstance(row, dict)
    assert row["image"] == {"uri": "/media/modified.png", "size": [80, 100]}


@pytest.mark.parametrize(
    "box",
    [
        {"x1": 0, "y1": 0, "x2": 101, "y2": 80},
        {"x1": 0, "y1": 0, "x2": 100, "y2": 81},
    ],
)
def test_crop_rejects_coordinates_outside_current_image(
    box: dict[str, JsonValue],
) -> None:
    # Given a 100 by 80 image.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the crop exceeds either current dimension.
                result = await session.call_tool(
                    "crop_page", {"document_id": 4, "page_id": 10, "box": box}
                )
                # Then no padded or destructive crop is submitted.
                assert result.is_error

        anyio.run(scenario)
    assert fixture.requests == [("GET", PAGE, None)]


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, [20, 40, 10, 30, 50]),
        (4, [10, 30, 20, 40, 50]),
        (-1, [10, 30, 50, 20, 40]),
        (5, [10, 30, 50, 20, 40]),
    ],
)
def test_bulk_move_uses_existing_relative_order(
    index: int, expected: list[int]
) -> None:
    # Given a paginated document ordered 10,20,30,40,50.
    with page_fixture(paginated=True) as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When IDs are supplied in reverse order to the native bulk action.
                result = await invoke(
                    session,
                    "bulk_move_pages",
                    {"document_id": 4, "move": {"page_ids": [40, 20], "index": index}},
                )
                # Then the raw status and server-defined relative order are retained.
                assert result == {"status": "moved"}

        anyio.run(scenario)
    assert fixture.requests[-1] == (
        "POST",
        DOC + "bulk_move_parts/",
        {"parts": [40, 20], "index": index},
    )
    assert [row["pk"] for row in fixture.rows if isinstance(row, dict)] == expected


@pytest.mark.parametrize(
    "move", [{"page_ids": [10, 99], "index": 0}, {"page_ids": [10], "index": 6}]
)
def test_bulk_move_preflight_refuses_foreign_ids_or_outside_index(
    move: dict[str, JsonValue],
) -> None:
    # Given five pages in the authorized document.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When the complete selection or insertion position is invalid.
                result = await session.call_tool(
                    "bulk_move_pages", {"document_id": 4, "move": move}
                )
                # Then the backend cannot silently ignore the foreign selection.
                assert result.is_error

        anyio.run(scenario)
    assert all(method == "GET" for method, _, _ in fixture.requests)


def test_bulk_move_requires_document_permission() -> None:
    # Given the document denies the caller permission.
    with page_fixture() as fixture:
        fixture.failures[DOC] = 403

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When a bulk route with weaker upstream scoping is requested.
                result = await session.call_tool(
                    "bulk_move_pages",
                    {"document_id": 4, "move": {"page_ids": [10], "index": 0}},
                )
                # Then preflight blocks the write.
                assert result.is_error

        anyio.run(scenario)
    assert fixture.requests == [("GET", DOC, None)]


def test_page_action_discovery_marks_destructive_nonidempotent_writes() -> None:
    # Given the public tool catalogue includes image upload and transformation.
    with page_fixture() as fixture:

        async def scenario() -> None:
            async with page_session(fixture) as session:
                # When a client discovers action safety annotations.
                catalogue = await session.list_tools()
                # Then file replacement and reordering are advertised truthfully.
                tools = {tool.name: tool for tool in catalogue.tools}
                for name in (
                    "upload_page",
                    "replace_page_image",
                    "rotate_page",
                    "crop_page",
                    "bulk_move_pages",
                ):
                    annotation = tools[name].annotations
                    assert annotation is not None
                    assert annotation.read_only_hint is False
                    assert annotation.destructive_hint is True
                    assert annotation.idempotent_hint is False

        anyio.run(scenario)
    assert fixture.requests == []
