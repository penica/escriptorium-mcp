"""Report-level summaries retain failures and distinguish absent history."""

import anyio
import pytest

from tests.ontology_fixture import invoke
from tests.task_fixture import TaskFixture, report, task_fixture, task_session


@pytest.mark.parametrize(
    ("states", "counts", "terminal", "flags"),
    [
        (
            [],
            {
                "queued": 0,
                "running": 0,
                "crashed": 0,
                "finished": 0,
                "canceled": 0,
                "unknown": 0,
            },
            0,
            (False, False, False),
        ),
        (
            [3],
            {
                "queued": 0,
                "running": 0,
                "crashed": 0,
                "finished": 1,
                "canceled": 0,
                "unknown": 0,
            },
            1,
            (True, False, False),
        ),
        (
            [0, 1, 2, 3, 4, 99],
            {
                "queued": 1,
                "running": 1,
                "crashed": 1,
                "finished": 1,
                "canceled": 1,
                "unknown": 1,
            },
            3,
            (False, True, True),
        ),
    ],
)
def test_document_summary_distinguishes_success_failure_and_unknown(
    states: list[int],
    counts: dict[str, int],
    terminal: int,
    flags: tuple[bool, bool, bool],
) -> None:
    rows = [report(pk, state) for pk, state in enumerate(states, 1)]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(
                session, "get_document_job_status", {"document_id": 7, "group_id": 4}
            )
            assert isinstance(result, dict)
            assert result["scope"] == "current_user_task_reports"
            assert result["document_id"] == 7
            assert result["group_id"] == 4
            assert result["counts"] == counts
            assert result["total"] == len(rows)
            assert result["terminal_count"] == terminal
            assert result["terminal_percent"] == (
                terminal / len(rows) * 100 if rows else None
            )
            assert result["all_finished"] is flags[0]
            assert result["has_failures"] is flags[1]
            assert result["has_active"] is flags[2]
            assert result["reports"] == rows

    with task_fixture(rows) as fixture:
        anyio.run(run, fixture)


def test_import_status_only_includes_import_reports() -> None:
    rows = [report(1, 0), report(2, 3, "imports.tasks.document_import")]

    async def run(fixture: TaskFixture) -> None:
        async with task_session(fixture) as session:
            result = await invoke(session, "get_import_status", {"document_id": 7})
            assert isinstance(result, dict)
            assert result["reports"] == [rows[1]]
            assert result["total"] == 1
            assert result["all_finished"] is True
            assert "processed" not in result

    with task_fixture(rows) as fixture:
        anyio.run(run, fixture)
