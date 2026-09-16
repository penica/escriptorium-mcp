"""Import group discovery remains uncertain and never changes acceptance."""

import anyio
import pytest
from pydantic import JsonValue

from tests.import_fixture import (
    IMPORT,
    METHOD,
    ImportFixture,
    import_fixture,
    import_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    ("new_groups", "status", "candidate_ids"),
    [
        ([], "none", []),
        ([{"pk": 2, "method": METHOD, "custom": "retained"}], "candidate", [2]),
        ([{"pk": 2, "method": None}], "candidate", [2]),
        ([{"pk": 2}], "candidate", [2]),
        (
            [
                {"pk": 2, "method": METHOD},
                {"pk": 3, "method": None},
                {"pk": 4, "method": "core.tasks.train"},
            ],
            "ambiguous",
            [2, 3],
        ),
        ([{"pk": 2, "method": "core.tasks.train"}], "none", []),
    ],
)
def test_tracking_reports_only_unconfirmed_import_candidates(
    new_groups: list[JsonValue], status: str, candidate_ids: list[int]
) -> None:
    # Given existing history and possibly concurrent new task groups.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When a single tracked submission is accepted.
            result = await invoke(
                session,
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "iiif_url",
                        "url": "https://example.org/manifest.json",
                    },
                    "track": True,
                },
            )
            # Then groups remain candidates, including one matching group.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"status": "ok"}
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == status
            assert tracking["attribution_confirmed"] is False
            candidates = tracking["candidates"]
            assert isinstance(candidates, list)
            ids: list[JsonValue] = []
            for candidate in candidates:
                assert isinstance(candidate, dict)
                ids.append(candidate["pk"])
                assert candidate in new_groups
            assert ids == candidate_ids

    with import_fixture() as fixture:
        fixture.groups_after[:] = [*fixture.groups_before, *new_groups]
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1


@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("failure", ["http", "parse"])
def test_monitoring_failure_retains_accepted_import(phase: str, failure: str) -> None:
    # Given monitoring denied or returning malformed task groups.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the import itself succeeds.
            result = await invoke(
                session,
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "iiif_url",
                        "url": "https://example.org/manifest.json",
                    },
                    "track": True,
                },
            )
            # Then monitoring cannot turn acceptance into a retryable failure.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"status": "ok"}
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == "unavailable"
            assert tracking["candidates"] == []
            assert tracking["attribution_confirmed"] is False

    with import_fixture() as fixture:
        if failure == "http":
            fixture.failures[phase] = 403
        else:
            fixture.responses[phase] = [{"pk": "invalid"}]
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1


@pytest.mark.parametrize("status", [400, 403, 500])
def test_failed_submission_is_not_retried(status: int) -> None:
    # Given a quota, permission or parser/database failure on POST.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the native submission fails.
            result = await session.call_tool(
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "iiif_url",
                        "url": "https://example.org/manifest.json",
                    },
                    "track": True,
                },
            )
            # Then the tool preserves failure and never claims accepted completion.
            assert result.is_error
            assert str(status) in result.model_dump_json()
            assert "may already exist" in result.model_dump_json()

    with import_fixture() as fixture:
        fixture.failures[IMPORT] = status
        anyio.run(run, fixture)
    assert [r for r in fixture.requests if r[0] == "POST"] == [
        (
            "POST",
            IMPORT,
            {"mode": "iiif", "iiif_uri": "https://example.org/manifest.json"},
        )
    ]


def test_bare_group_lists_preserve_candidate_metadata() -> None:
    # Given an unpaginated server response with additional group fields.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When a tracked import creates one new candidate.
            result = await invoke(
                session,
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "iiif_url",
                        "url": "https://example.org/manifest.json",
                    },
                    "track": True,
                },
            )
            # Then the complete candidate record is preserved.
            assert isinstance(result, dict)
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["candidates"] == [
                {"pk": 5, "method": METHOD, "custom": "keep"}
            ]

    with import_fixture() as fixture:
        fixture.responses["before"] = [{"pk": 1, "method": METHOD}]
        fixture.responses["after"] = [
            {"pk": 1, "method": METHOD},
            {"pk": 5, "method": METHOD, "custom": "keep"},
        ]
        anyio.run(run, fixture)


def test_lost_submission_response_is_not_retried() -> None:
    # Given an upstream accepting the POST but closing before sending its response.
    async def run(fixture: ImportFixture) -> None:
        async with import_session(fixture) as session:
            # When the submission response is lost.
            result = await session.call_tool(
                "submit_document_import",
                {
                    "document_id": 4,
                    "source": {
                        "kind": "iiif_url",
                        "url": "https://example.org/manifest.json",
                    },
                    "track": True,
                },
            )
            # Then failure retains uncertainty about effects and does not trigger retry.
            assert result.is_error
            assert "may already exist" in result.model_dump_json()

    with import_fixture() as fixture:
        fixture.disconnect.add(IMPORT)
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1
