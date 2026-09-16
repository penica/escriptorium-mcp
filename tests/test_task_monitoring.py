"""Task monitoring contracts exercised through MCP STDIO and the real worker."""

from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from mcp_types import TextContent
from pydantic import JsonValue, TypeAdapter

from tests.ontology_fixture import invoke
from tests.task_fixture import TaskFixture, report, task_fixture, task_session


def test_task_filter_matches_second_page_and_preserves_server_filters() -> None:
    rows = [report(1, 1), report(2, 3, "imports.tasks.document_import")]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(
                session,
                "list_tasks",
                {
                    "document_id": 7,
                    "group_id": 4,
                    "ordering": "-queued_at,started_at",
                    "workflow_state": 3,
                    "method": "imports.tasks.document_import",
                },
            )
            assert isinstance(result, dict)
            assert result["results"] == [rows[1]]
            assert result["count"] == 1
            assert result["next"] is None

    with task_fixture(rows) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 2
    for method, path, _body in fixture.requests:
        assert method == "GET"
        query = parse_qs(urlsplit(path).query)
        assert query["document"] == ["7"]
        assert query["group"] == ["4"]
        assert query["ordering"] == ["-queued_at,started_at"]
        assert "workflow_state" not in query
        assert "method" not in query


def test_unfiltered_tasks_keep_paginated_envelope() -> None:
    rows = [report(1, 0), report(2, 3)]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(session, "list_tasks", {})
            assert result == {"count": 2, "next": None, "results": rows}

    with task_fixture(rows) as fixture:
        anyio.run(run, fixture)


def test_document_task_listing_sends_supported_query() -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(
                session,
                "list_document_tasks",
                {"name": "Register & notes", "task_state": "running", "user_id": 2},
            )
            assert result == {"count": 1, "next": None, "results": [{"pk": 7}]}

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    method, path, _body = fixture.requests[0]
    assert method == "GET"
    assert parse_qs(urlsplit(path).query) == {
        "name": ["Register & notes"],
        "task_state": ["running"],
        "user_id": ["2"],
    }


@pytest.mark.parametrize("tool", ["list_task_groups", "get_task_group"])
def test_task_group_reads(tool: str) -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            args: dict[str, JsonValue] = {"document_id": 7}
            if tool == "get_task_group":
                args["group_id"] = 4
            result = await invoke(session, tool, args)
            assert isinstance(result, dict)
            if tool == "get_task_group":
                assert result["pk"] == 4
                assert result["page_count"] == 1
            else:
                assert result["count"] == 1

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _path, _body in fixture.requests)


@pytest.mark.parametrize(
    ("tool", "route"),
    [
        ("cancel_document_tasks", "cancel_tasks"),
        ("cancel_document_import", "cancel_import"),
    ],
)
def test_document_cancellation_posts_empty_body_without_preflight(
    tool: str,
    route: str,
) -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(session, tool, {"document_id": 7})
            assert result == {"status": "canceled"}

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("POST", f"/api/documents/7/{route}/", {})]


@pytest.mark.parametrize("status", [401, 404])
def test_monitoring_propagates_backend_errors(status: int) -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await session.call_tool(
                "get_document_job_status",
                {"document_id": 7},
            )
            assert result.is_error
            assert str(status) in str(result.content)

    with task_fixture([], status=status) as fixture:
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", "/api/documents/7/", None)]


@pytest.mark.parametrize(
    "arguments",
    [
        {"ordering": "label"},
        {"ordering": "queued_at;delete"},
        {"workflow_state": 5},
        {"document_id": 0},
    ],
)
def test_invalid_task_filters_do_not_reach_http(
    arguments: dict[str, JsonValue],
) -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await session.call_tool("list_tasks", arguments)
            assert result.is_error

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


def test_monitoring_discovery_reports_read_and_destructive_annotations() -> None:
    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            response = await session.list_tools()
            tools = {tool.name: tool for tool in response.tools}
            for name in [
                "list_tasks",
                "list_document_tasks",
                "list_task_groups",
                "get_task_group",
                "get_document_job_status",
                "get_import_status",
            ]:
                annotations = tools[name].annotations
                assert annotations is not None
                assert annotations.read_only_hint is True
            for name in ["cancel_document_tasks", "cancel_document_import"]:
                annotations = tools[name].annotations
                assert annotations is not None
                assert annotations.read_only_hint is False
                assert annotations.destructive_hint is True

    with task_fixture([]) as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize("arguments", [{}, {"workflow_state": 3}])
def test_plain_list_task_responses(
    arguments: dict[str, JsonValue],
) -> None:
    rows = [report(1, 0), report(2, 3)]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            response = await session.call_tool("list_tasks", arguments)
            assert not response.is_error
            values: list[JsonValue] = []
            for content in response.content:
                assert isinstance(content, TextContent)
                values.append(
                    TypeAdapter[JsonValue](JsonValue).validate_json(content.text)
                )
            if arguments:
                result = values[0]
                assert isinstance(result, dict)
                assert result["results"] == [rows[1]]
                assert result["count"] == 1
            else:
                assert values == rows

    with task_fixture(rows, plain_list=True) as fixture:
        anyio.run(run, fixture)
