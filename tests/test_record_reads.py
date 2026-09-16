"""Raw record reads preserve native fields, filters and ordered lookup shapes."""

from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import anyio
import pytest

from tests.record_fixture import (
    DOCUMENT,
    DOCUMENTS,
    PROJECT,
    PROJECTS,
    RecordFixture,
    record_fixture,
    record_session,
)
from tests.transcription_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_unfiltered_lists_share_raw_path_and_preserve_modern_fields() -> None:
    # Given expanded native sharing, tags, fonts, nulls, zeroes and future fields.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When clients omit filters, supply null, or supply an empty object.
            for tool, expected in [
                ("list_projects", fixture.project),
                ("list_documents", fixture.document),
            ]:
                variants: list[dict[str, JsonValue]] = [
                    {},
                    {"filters": None},
                    {"filters": {}},
                ]
                for args in variants:
                    result = await invoke(session, tool, args)
                    # Then every form returns the unmodified first record.
                    assert isinstance(result, dict)
                    rows = result["results"]
                    assert isinstance(rows, list)
                    assert rows[0] == expected
                    assert result["next"] is None

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r[1] for r in fixture.requests] == [PROJECTS] * 3 + [DOCUMENTS] * 3


def test_details_preserve_exact_native_representation_and_sparse_records() -> None:
    # Given raw project id/document pk records with new fields and Z timestamps.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When detail methods read their canonical routes.
            assert (
                await invoke(session, "get_project", {"project_id": 1})
                == fixture.project
            )
            assert (
                await invoke(session, "get_document", {"document_id": 4})
                == fixture.document
            )
            fixture.responses[PROJECT] = {"id": 1}
            # Then absent optional fields remain absent rather than gaining defaults.
            assert await invoke(session, "get_project", {"project_id": 1}) == {"id": 1}

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r[1] for r in fixture.requests] == [PROJECT, DOCUMENT, PROJECT]


def test_native_filters_and_paginated_or_duplicates_are_preserved() -> None:
    # Given an OR-filtered collection whose second page repeats the first record.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When native search, tag grammar, numeric project and ordering are used.
            result = await invoke(
                session,
                "list_documents",
                {
                    "filters": {
                        "name": "Parish č",
                        "project": 1,
                        "tags": "11|21",
                        "ordering": ["-parts_count", "name"],
                    }
                },
            )
            # Then duplicates and server counts remain native, with pagination drained.
            assert result == {
                "count": 9,
                "next": None,
                "previous": "retained",
                "results": [fixture.document, fixture.document],
            }
            _ = await invoke(
                session,
                "list_projects",
                {
                    "filters": {
                        "name": "Old",
                        "tags": "none|31",
                        "ordering": ["-documents_count", "id"],
                    }
                },
            )

    with record_fixture() as fixture:
        fixture.responses[DOCUMENTS] = {
            "count": 9,
            "next": DOCUMENTS + "?page=2",
            "previous": "retained",
            "results": [fixture.document],
        }
        fixture.responses[DOCUMENTS + "?page=2"] = {
            "count": 9,
            "next": None,
            "results": [fixture.document],
        }
        anyio.run(run, fixture)
    assert parse_qs(urlsplit(fixture.requests[0][1]).query) == {
        "name": ["Parish č"],
        "project": ["1"],
        "tags": ["11|21"],
        "ordering": ["-parts_count,name"],
    }
    assert fixture.requests[1][1] == DOCUMENTS + "?page=2"
    assert parse_qs(urlsplit(fixture.requests[2][1]).query) == {
        "name": ["Old"],
        "tags": ["none|31"],
        "ordering": ["-documents_count,id"],
    }


def test_bare_record_collection_is_not_rewrapped() -> None:
    # Given an upstream returning a valid bare collection instead of pagination.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When both ordinary record list methods are called.
            # Then the list shape and empty result are preserved.
            assert await invoke(session, "list_projects", {}) == [fixture.project]
            assert await invoke(session, "list_documents", {}) == []

    with record_fixture() as fixture:
        fixture.responses[PROJECTS] = [fixture.project]
        fixture.responses[DOCUMENTS] = []
        anyio.run(run, fixture)


def test_statistics_options_and_raw_page_ids() -> None:
    # Given geometry statistics with untyped null fields and a zero frequency.
    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When default, explicit false and refreshing ordered reads are requested.
            variants: list[JsonValue] = [
                None,
                {},
                {"refresh": False},
                {"refresh": True, "ordering": "-taxonomy"},
            ]
            for options in variants:
                args: dict[str, JsonValue] = {"document_id": 4, "options": options}
                result = await invoke(session, "get_document_statistics", args)
                # Then statistics retain their native null/zero structure.
                assert isinstance(result, dict)
                assert result["regions"] == [
                    {
                        "typology_id": None,
                        "typology_name": None,
                        "typology_color": None,
                        "frequency": 0,
                    }
                ]
            assert await invoke(
                session, "list_document_page_ids", {"document_id": 4}
            ) == [12, 11]
            fixture.responses[DOCUMENT + "part_ids/"] = []
            assert (
                await invoke(session, "list_document_page_ids", {"document_id": 4})
                == []
            )

    with record_fixture() as fixture:
        anyio.run(run, fixture)
    stats = [r for r in fixture.requests if urlsplit(r[1]).path.endswith("/stats/")]
    assert [parse_qs(urlsplit(r[1]).query) for r in stats] == [
        {},
        {},
        {"refresh": ["false"]},
        {"refresh": ["true"], "ordering": ["-taxonomy"]},
    ]


@pytest.mark.parametrize(
    ("category", "id_key"),
    [
        ("regions", "document_part_id"),
        ("lines", "document_part_id"),
        ("text", "part_id"),
        ("image", "part_id"),
    ],
)
def test_element_page_lookup_preserves_category_specific_ids(
    category: str, id_key: str
) -> None:
    # Given category-specific native page identity keys.
    selected_type: JsonValue = 3 if category in {"text", "image"} else "none"
    expected: JsonValue = {
        "parts": [
            {id_key: 12, "part_name": None, "part_filename": "page.png", "frequency": 0}
        ]
    }

    async def run(fixture: RecordFixture) -> None:
        async with record_session(fixture) as session:
            # When the public type_id maps to the native type parameter.
            result = await invoke(
                session,
                "find_pages_by_type",
                {
                    "document_id": 4,
                    "query": {"category": category, "type_id": selected_type},
                },
            )
            # Then no category-specific identity aliases are invented.
            assert result == expected

    with record_fixture() as fixture:
        fixture.responses[DOCUMENT + "elements_by_type/"] = expected
        anyio.run(run, fixture)
    assert parse_qs(urlsplit(fixture.requests[-1][1]).query) == {
        "category": [category],
        "type": [str(selected_type)],
    }
