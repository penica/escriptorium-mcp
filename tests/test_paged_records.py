from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from pydantic import JsonValue, TypeAdapter

from tests.model_fixture import ModelFixture, model_fixture, model_session
from tests.ontology_fixture import invoke
from tests.page_fixture import PageFixture, page_fixture, page_session
from tests.record_fixture import (
    DOCUMENTS,
    RecordFixture,
    record_fixture,
    record_session,
)
from tests.transcription_fixture import (
    TranscriptionFixture,
    transcription_fixture,
    transcription_session,
)


def test_document_page_selection_is_one_native_request_with_metadata() -> None:
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            result = await invoke(
                session,
                "list_documents",
                {"pagination": {"page": 2, "page_size": 1}},
            )
            assert isinstance(result, dict)
            assert result["results"] == [fixture.document]
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["page"] == 2
            assert metadata["page_size"] == 1
            assert metadata["returned_count"] == 1
            assert metadata["native_total"] == 3

    with record_fixture() as fixture:
        fixture.responses[DOCUMENTS + "?page=2&paginate_by=1"] = {
            "count": 3,
            "next": "?page=3&paginate_by=1",
            "previous": "?page=1&paginate_by=1",
            "results": [fixture.document],
        }
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", DOCUMENTS + "?page=2&paginate_by=1", None)]


def test_page_selection_uses_native_page_without_page_size() -> None:
    async def run(fixture: PageFixture) -> None:
        async with page_session(fixture) as session:
            result = await invoke(
                session,
                "list_pages",
                {"document_id": 4, "pagination": {"page": 2}},
            )
            assert isinstance(result, dict)
            assert result["results"] == fixture.rows[1:]
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["page"] == 2
            assert metadata["page_size"] is None

    with page_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert parse_qs(urlsplit(fixture.requests[0][1]).query) == {"page": ["2"]}


def test_page_size_is_rejected_for_page_transcriptions_before_http() -> None:
    async def run(fixture: TranscriptionFixture) -> None:
        async with transcription_session(fixture) as session:
            response = await session.call_tool(
                "get_page_transcriptions",
                {
                    "document_id": 4,
                    "page_id": 10,
                    "pagination": {"page": 1, "page_size": 2},
                },
            )
            assert response.is_error

    with transcription_fixture(paginated=True) as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize(
    ("tool", "route", "page_size_supported"),
    [
        ("list_lines", "/api/documents/4/parts/10/lines/", True),
        ("list_regions", "/api/documents/4/parts/10/blocks/", True),
        (
            "get_page_transcriptions",
            "/api/documents/4/parts/10/transcriptions/",
            False,
        ),
    ],
)
def test_nested_record_lists_select_one_native_page(
    tool: str, route: str, *, page_size_supported: bool
) -> None:
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            args: dict[str, JsonValue] = {
                "document_id": 4,
                "page_id": 10,
                "pagination": {"page": 2},
            }
            if page_size_supported:
                pagination = args["pagination"]
                assert isinstance(pagination, dict)
                pagination["page_size"] = 1
            result = await invoke(session, tool, args)
            assert isinstance(result, dict)
            assert result["results"] == [{"pk": 2}]
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["page"] == 2

    query = "?page=2&paginate_by=1" if page_size_supported else "?page=2"
    with record_fixture() as fixture:
        fixture.responses[route + query] = {
            "count": 3,
            "next": None,
            "previous": ("?page=1&paginate_by=1" if page_size_supported else "?page=1"),
            "results": [{"pk": 2}],
        }
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", route + query, None)]


def test_model_page_preserves_filters_and_supports_native_page_size() -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await invoke(
                session,
                "list_models",
                {
                    "document_id": 4,
                    "job": 1,
                    "pagination": {"page": 3, "page_size": 5},
                },
            )
            assert isinstance(result, dict)
            metadata = result["pagination"]
            assert isinstance(metadata, dict)
            assert metadata["page"] == 3
            assert metadata["page_size"] == 5

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert parse_qs(urlsplit(fixture.requests[0].path).query) == {
        "documents": ["4"],
        "job": ["1"],
        "page": ["3"],
        "paginate_by": ["5"],
    }


@pytest.mark.parametrize(
    "tool",
    [
        "list_projects",
        "list_documents",
        "list_pages",
        "list_lines",
        "list_regions",
        "get_page_transcriptions",
        "list_models",
    ],
)
def test_record_list_schema_exposes_optional_pagination(tool: str) -> None:
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            catalogue = {item.name: item for item in (await session.list_tools()).tools}
            schema = TypeAdapter[dict[str, JsonValue]](
                dict[str, JsonValue]
            ).validate_python(catalogue[tool].input_schema)
            properties = schema["properties"]
            assert isinstance(properties, dict)
            assert "pagination" in properties

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests
