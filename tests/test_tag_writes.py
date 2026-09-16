"""Tag definition mutations use exact native bodies and scoped routes."""

import anyio
import pytest
from pydantic import JsonValue

from tests.tag_fixture import PERSONAL, PROJECT, PROJECT_TAGS, tag_fixture, tag_session
from tests.transcription_fixture import invoke


@pytest.mark.parametrize("personal", [False, True])
@pytest.mark.parametrize("color", [None, "strange"])
def test_create_tag_preserves_native_default(
    *, personal: bool, color: str | None
) -> None:
    target: dict[str, JsonValue] = (
        {"scope": "personal_projects"}
        if personal
        else {"scope": "project_documents", "project_id": 7}
    )
    base = PERSONAL if personal else PROJECT_TAGS
    data: dict[str, JsonValue] = {"name": "New tag"}
    if color is not None:
        data["color"] = color
    with tag_fixture() as fixture:

        async def run() -> None:
            async with tag_session(fixture) as session:
                result = await invoke(
                    session, "create_tag", {"target": target, "data": data}
                )
                assert isinstance(result, dict)
                assert result["name"] == "New tag"
                assert result["color"] == (color or "#123456")

        anyio.run(run)
    expected = [] if personal else [("GET", PROJECT, None)]
    assert fixture.requests == [*expected, ("POST", base, data)]


@pytest.mark.parametrize("personal", [False, True])
@pytest.mark.parametrize("changes", [{"name": "Renamed"}, {"color": "red"}])
def test_patch_changes_only_the_definition_fields(
    *, personal: bool, changes: dict[str, JsonValue]
) -> None:
    target: dict[str, JsonValue] = (
        {"scope": "personal_projects"}
        if personal
        else {"scope": "project_documents", "project_id": 7}
    )
    base = PERSONAL if personal else PROJECT_TAGS
    with tag_fixture() as fixture:

        async def run() -> None:
            async with tag_session(fixture) as session:
                result = await invoke(
                    session,
                    "update_tag",
                    {"target": target, "tag_id": 2, "changes": changes},
                )
                assert isinstance(result, dict)
                assert result["name"] == changes.get("name", "Review")
                assert result["color"] == changes.get("color", "#123456")

        anyio.run(run)
    expected = [] if personal else [("GET", PROJECT, None)]
    assert fixture.requests == [
        *expected,
        ("GET", base + "2/", None),
        ("PATCH", base + "2/", changes),
    ]


@pytest.mark.parametrize("personal", [False, True])
def test_delete_definition_never_deletes_a_project_or_document(
    *, personal: bool
) -> None:
    target: dict[str, JsonValue] = (
        {"scope": "personal_projects"}
        if personal
        else {"scope": "project_documents", "project_id": 7}
    )
    base = PERSONAL if personal else PROJECT_TAGS
    with tag_fixture() as fixture:

        async def run() -> None:
            async with tag_session(fixture) as session:
                result = await invoke(
                    session, "delete_tag", {"target": target, "tag_id": 2}
                )
                assert result == {"status": "success", "http_status": 204}

        anyio.run(run)
    expected = [] if personal else [("GET", PROJECT, None)]
    assert fixture.requests == [
        *expected,
        ("GET", base + "2/", None),
        ("DELETE", base + "2/", {}),
    ]


@pytest.mark.parametrize("status", [400, 403, 404, 409, 500])
def test_creation_failure_is_not_retried(status: int) -> None:
    with tag_fixture() as fixture:
        fixture.failures[PERSONAL] = status

        async def run() -> None:
            async with tag_session(fixture) as session:
                result = await session.call_tool(
                    "create_tag",
                    {"target": {"scope": "personal_projects"}, "data": {"name": "New"}},
                )
                assert result.is_error
                assert "fixture-key" not in str(result.content)

        anyio.run(run)
    assert fixture.requests == [("POST", PERSONAL, {"name": "New"})]


@pytest.mark.parametrize("tool", ["update_tag", "delete_tag"])
def test_scoped_mutation_failure_is_not_retried(tool: str) -> None:
    method = "PATCH" if tool == "update_tag" else "DELETE"
    detail = PROJECT_TAGS + "2/"
    with tag_fixture() as fixture:
        fixture.failures[f"{method} {detail}"] = 500

        async def run() -> None:
            async with tag_session(fixture) as session:
                args: dict[str, JsonValue] = {
                    "target": {"scope": "project_documents", "project_id": 7},
                    "tag_id": 2,
                }
                if tool == "update_tag":
                    args["changes"] = {"name": "Revised"}
                response = await session.call_tool(tool, args)
                assert response.is_error
                assert "500" in str(response.content)

        anyio.run(run)
    assert fixture.requests == [
        ("GET", PROJECT, None),
        ("GET", detail, None),
        (method, detail, {"name": "Revised"} if method == "PATCH" else {}),
    ]
