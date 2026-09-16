"""Ordinary alignment monitoring retains acceptance and uncertain attribution."""

import anyio
import pytest
from pydantic import JsonValue

from tests.alignment_fixture import (
    AlignmentFixture,
    alignment_fixture,
    alignment_job,
    alignment_session,
)
from tests.transcription_fixture import invoke


@pytest.mark.parametrize(
    ("groups", "status", "ids"),
    [
        ([], "none", []),
        ([{"pk": 2, "method": "core.tasks.align", "custom": "keep"}], "candidate", [2]),
        ([{"pk": 2, "method": None}], "candidate", [2]),
        (
            [
                {"pk": 2, "method": "core.tasks.align"},
                {"pk": 3},
                {"pk": 4, "method": "core.tasks.train"},
            ],
            "ambiguous",
            [2, 3],
        ),
    ],
)
def test_alignment_groups_remain_unconfirmed_candidates(
    groups: list[JsonValue], status: str, ids: list[int]
) -> None:
    # Given old alignment history and potentially concurrent new groups.
    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When one ordinary alignment is tracked across its submission.
            result = await invoke(
                session,
                "align_document",
                {"document_id": 4, "job": alignment_job(), "track": True},
            )
            # Then a matching group is a candidate, never a confirmed task identity.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"status": "ok"}
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == status
            assert tracking["attribution_confirmed"] is False
            candidates = tracking["candidates"]
            assert isinstance(candidates, list)
            found: list[JsonValue] = []
            for candidate in candidates:
                assert isinstance(candidate, dict)
                found.append(candidate["pk"])
                assert candidate in groups
            assert found == ids

    with alignment_fixture() as fixture:
        fixture.groups_after[:] = [*fixture.groups_before, *groups]
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1


@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("failure", ["http", "parse"])
def test_monitoring_failure_does_not_erase_alignment_acceptance(
    phase: str, failure: str
) -> None:
    # Given denied or malformed optional group discovery.
    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When the alignment itself is accepted.
            result = await invoke(
                session,
                "align_document",
                {"document_id": 4, "job": alignment_job(), "track": True},
            )
            # Then failed monitoring cannot invite another mutation.
            assert isinstance(result, dict)
            assert result["accepted"] is True
            assert result["submission"] == {"status": "ok"}
            tracking = result["tracking"]
            assert isinstance(tracking, dict)
            assert tracking["status"] == "unavailable"
            assert tracking["candidates"] == []
            assert tracking["attribution_confirmed"] is False

    with alignment_fixture() as fixture:
        if failure == "http":
            fixture.failures[phase] = 403
        else:
            fixture.responses[phase] = [{"pk": "bad"}]
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1
