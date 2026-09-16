"""Action-specific font capability and identity checks precede native mutations."""

import anyio
import pytest
from pydantic import JsonValue

from tests.font_fixture import FONT, FontFixture, font_fixture, font_session
from tests.font_write_cases import OPERATIONS, Operation, write_case
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("scenario", ["missing", "read_only", "wrong_method", "denied"])
def test_unsupported_font_clear_never_writes(
    operation: Operation, scenario: str
) -> None:
    # Given metadata that cannot authorize this particular write, even for null.
    case = write_case(operation, {"transcription_font": None})
    method = "POST" if case.method == "POST" else "PATCH"
    field: dict[str, JsonValue] = {"transcription_font": {"read_only": False}}
    actions: dict[str, JsonValue] = {method: field}
    if scenario == "missing":
        actions[method] = {}
    elif scenario == "read_only":
        actions[method] = {"transcription_font": {"read_only": True}}
    elif scenario == "wrong_method":
        actions = {"GET": field}

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the caller clears the preference, then no mutation is attempted.
            result = await session.call_tool(case.tool, case.arguments)
            assert result.is_error

    with font_fixture() as fixture:
        if scenario == "denied":
            fixture.failures["OPTIONS " + case.route] = 403
        else:
            fixture.responses["OPTIONS " + case.route] = {"actions": actions}
        anyio.run(run, fixture)
    assert fixture.requests == [("OPTIONS", case.route, None)]


@pytest.mark.parametrize("permission", [{}, {"read_only": "false"}])
def test_missing_or_coercible_write_permission_blocks_clear(
    permission: dict[str, JsonValue],
) -> None:
    # Given missing or string-encoded permission instead of explicit boolean false.
    case = write_case("document_update", {"transcription_font": None})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When clearing a font, then ambiguous permission blocks the write.
            assert (await session.call_tool(case.tool, case.arguments)).is_error

    with font_fixture() as fixture:
        fixture.responses["OPTIONS " + case.route] = {
            "actions": {"PATCH": {"transcription_font": permission}}
        }
        anyio.run(run, fixture)
    assert fixture.requests == [("OPTIONS", case.route, None)]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("scenario", ["missing", "mismatched"])
def test_unreadable_or_wrong_font_prevents_write(
    operation: Operation, scenario: str
) -> None:
    # Given a writable setting whose selected font is missing or has the wrong identity.
    case = write_case(operation, {"transcription_font": 3})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the font detail is checked, then no assignment reaches the server.
            assert (await session.call_tool(case.tool, case.arguments)).is_error

    with font_fixture() as fixture:
        if scenario == "missing":
            fixture.failures["GET " + FONT] = 404
        else:
            fixture.responses["GET " + FONT] = {"pk": 99, "name": "Other"}
        anyio.run(run, fixture)
    assert fixture.requests == [("OPTIONS", case.route, None), ("GET", FONT, None)]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_native_assignment_failure_is_one_write(operation: Operation) -> None:
    # Given a native mutation failure after positive capability and font checks.
    case = write_case(operation, {"transcription_font": 3})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When the write fails, then the failure is surfaced without retry.
            result = await session.call_tool(case.tool, case.arguments)
            assert result.is_error
            assert "500" in str(result.content)

    with font_fixture() as fixture:
        fixture.failures[case.method + " " + case.route] = 500
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("OPTIONS", case.route, None),
        ("GET", FONT, None),
        (case.method, case.route, case.body),
    ]


@pytest.mark.parametrize("operation", ["project_update", "document_update"])
def test_patch_uses_native_put_metadata_when_patch_absent(operation: Operation) -> None:
    # Given DRF OPTIONS exposing writable PUT fields without a PATCH action.
    case = write_case(operation, {"transcription_font": None})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When clearing via PATCH, then native PUT field capability is sufficient.
            assert await invoke(session, case.tool, case.arguments) == {
                "saved": case.body
            }

    with font_fixture() as fixture:
        fixture.responses["OPTIONS " + case.route] = {
            "actions": {"PUT": {"transcription_font": {"read_only": False}}}
        }
        anyio.run(run, fixture)
    assert fixture.requests == [
        ("OPTIONS", case.route, None),
        ("PATCH", case.route, case.body),
    ]


@pytest.mark.parametrize("operation", ["project_update", "document_update"])
def test_explicit_patch_restriction_is_not_bypassed_using_put(
    operation: Operation,
) -> None:
    # Given a restricted PATCH action alongside a writable PUT action.
    case = write_case(operation, {"transcription_font": None})

    async def run(fixture: FontFixture) -> None:
        async with font_session(fixture) as session:
            # When PATCH is restricted, then PUT cannot override it.
            assert (await session.call_tool(case.tool, case.arguments)).is_error

    with font_fixture() as fixture:
        fixture.responses["OPTIONS " + case.route] = {
            "actions": {
                "PATCH": {},
                "PUT": {"transcription_font": {"read_only": False}},
            }
        }
        anyio.run(run, fixture)
    assert fixture.requests == [("OPTIONS", case.route, None)]
