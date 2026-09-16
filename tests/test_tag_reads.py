"""Tag reads retain native metadata and paginate within each scope."""

from typing import TYPE_CHECKING

import anyio
import pytest

from tests.tag_fixture import (
    PERSONAL,
    PROJECT,
    PROJECT_TAGS,
    TagFixture,
    tag_fixture,
    tag_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_personal_tag_list_preserves_response() -> None:
    async def run(fixture: TagFixture) -> None:
        async with tag_session(fixture) as session:
            result = await invoke(
                session, "list_tags", {"target": {"scope": "personal_projects"}}
            )
            assert result == {
                "count": 1,
                "next": None,
                "results": [fixture.tag],
                "extra": "keep",
            }

    with tag_fixture() as fixture:
        anyio.run(run, fixture)


@pytest.mark.parametrize("personal", [False, True])
def test_scoped_detail_preserves_unknown_fields(*, personal: bool) -> None:
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
                    session, "get_tag", {"target": target, "tag_id": 2}
                )
                assert result == fixture.tag

        anyio.run(run)
    expected = [] if personal else [("GET", PROJECT, None)]
    assert fixture.requests == [*expected, ("GET", base + "2/", None)]


@pytest.mark.parametrize("personal", [False, True])
def test_tag_list_follows_all_pages(*, personal: bool) -> None:
    target: dict[str, JsonValue] = (
        {"scope": "personal_projects"}
        if personal
        else {"scope": "project_documents", "project_id": 7}
    )
    base = PERSONAL if personal else PROJECT_TAGS
    with tag_fixture() as fixture:
        second: dict[str, JsonValue] = {
            "pk": 3,
            "name": "Second",
            "color": "red",
            "future": None,
        }
        fixture.responses[base] = {
            "count": 2,
            "next": fixture.url.rstrip("/") + base + "?page=2",
            "results": [fixture.tag],
            "extra": "keep",
        }
        fixture.responses[base + "?page=2"] = {
            "count": 2,
            "next": None,
            "results": [second],
        }

        async def run() -> None:
            async with tag_session(fixture) as session:
                result = await invoke(session, "list_tags", {"target": target})
                assert result == {
                    "count": 2,
                    "next": None,
                    "results": [fixture.tag, second],
                    "extra": "keep",
                }

        anyio.run(run)
    expected = [] if personal else [("GET", PROJECT, None)]
    assert fixture.requests == [
        *expected,
        ("GET", base, None),
        ("GET", base + "?page=2", None),
    ]
