from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from pydantic import JsonValue, TypeAdapter

from tests.ontology_fixture import invoke
from tests.task_fixture import TaskFixture, report, task_fixture, task_session


def test_task_local_filter_describes_only_the_selected_native_page() -> None:
    rows = [report(1, 0), report(2, 3)]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(
                session,
                "list_tasks",
                {"workflow_state": 3, "pagination": {"page": 1, "page_size": 1}},
            )
            assert isinstance(result, dict)
            assert result["results"] == []
            assert result["count"] is None
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["native_total"] == 2
            assert metadata["filtered_total"] == 0
            assert metadata["filtered_total_scope"] == "source_page"
            assert metadata["returned_count"] == 0

    with task_fixture(rows) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert parse_qs(urlsplit(fixture.requests[0][1]).query) == {
        "page": ["1"],
        "paginate_by": ["1"],
    }


def test_default_task_listing_remains_exhaustive_and_unchanged() -> None:
    rows = [report(1, 0), report(2, 3)]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(session, "list_tasks", {})
            assert result == {"count": 2, "next": None, "results": rows}

    with task_fixture(rows) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 2


def test_native_page_error_propagates_after_one_request() -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            response = await session.call_tool(
                "list_tasks", {"pagination": {"page": 9}}
            )
            assert response.is_error
            assert "404" in str(response.content)

    with task_fixture([], status=404) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert parse_qs(urlsplit(fixture.requests[0][1]).query) == {"page": ["9"]}


def test_task_group_page_size_is_forwarded_once() -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(
                session,
                "list_task_groups",
                {
                    "document_id": 7,
                    "pagination": {"page": 2, "page_size": 5},
                },
            )
            assert isinstance(result, dict)
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["page"] == 2
            assert metadata["page_size"] == 5

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert parse_qs(urlsplit(fixture.requests[0][1]).query) == {
        "page": ["2"],
        "paginate_by": ["5"],
    }


@pytest.mark.parametrize("tool", ["list_models", "list_tasks", "list_task_groups"])
def test_task_list_schema_exposes_optional_pagination(tool: str) -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            catalogue = {item.name: item for item in (await session.list_tools()).tools}
            schema = TypeAdapter[dict[str, JsonValue]](
                dict[str, JsonValue]
            ).validate_python(catalogue[tool].input_schema)
            properties = schema["properties"]
            assert isinstance(properties, dict)
            assert "pagination" in properties

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize(
    "pagination",
    [{"page": 0}, {"page": True}, {"page_size": 0}, {"page_size": 51}],
)
def test_invalid_task_pagination_never_reaches_http(
    pagination: dict[str, JsonValue],
) -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            response = await session.call_tool("list_tasks", {"pagination": pagination})
            assert response.is_error

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
