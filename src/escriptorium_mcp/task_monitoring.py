"""Paginated task filters and report-based progress, without inferred job progress."""

from collections import Counter
from typing import Annotated, ClassVar, Final, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from escriptorium_mcp.api import ApiRequest, Input, invoke
from escriptorium_mcp.bridge import Identifier, call

TaskState = Literal[0, 1, 2, 3, 4]
StateLabel = Literal["queued", "running", "crashed", "finished", "canceled"]
TaskOrdering = Annotated[
    str,
    Field(
        pattern=r"^-?(queued_at|started_at|done_at)(,-?(queued_at|started_at|done_at))*$"
    ),
]
IMPORT_METHOD: Final = "imports.tasks.document_import"
STATE_NAMES: Final = ("queued", "running", "crashed", "finished", "canceled")


class TaskFilters(Input):
    """Only supported server filters are forwarded; state and method stay local."""

    document_id: Identifier | None = None
    group_id: Identifier | None = None
    ordering: TaskOrdering | None = None
    workflow_state: TaskState | None = None
    method: str | None = None


class TaskRecord(BaseModel):
    """Require status evidence and preserve all upstream report fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    pk: Identifier
    workflow_state: Annotated[int, Field(strict=True)]
    method: str | None = None

    def as_json(self) -> JsonValue:
        """Retain custom server fields without introducing absent optional fields."""
        return TypeAdapter[JsonValue](JsonValue).validate_json(
            self.model_dump_json(exclude_unset=True)
        )


class TaskPage(BaseModel):
    """The worker follows all next links before returning this page."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    results: list[TaskRecord]


def task_records(value: JsonValue) -> list[TaskRecord]:
    """Accept both paginated and unpaginated API collection responses."""
    parsed = TypeAdapter[list[TaskRecord] | TaskPage](
        list[TaskRecord] | TaskPage
    ).validate_python(value)
    match parsed:
        case TaskPage(results=records):
            return records
        case list():
            return parsed
        case _:
            assert_never(parsed)


async def read_tasks(filters: TaskFilters) -> JsonValue:
    """Preserve legacy listing responses unless a local filter is requested."""
    query = {
        key: str(value)
        for key, value in (
            ("document", filters.document_id),
            ("group", filters.group_id),
            ("ordering", filters.ordering),
        )
        if value is not None
    }
    raw = await call(
        ApiRequest(method="GET", route="tasks/", paginate=True, query=query)
    )
    if filters.workflow_state is None and filters.method is None:
        return raw
    records = [
        report.as_json()
        for report in task_records(raw)
        if (
            filters.workflow_state is None
            or report.workflow_state == filters.workflow_state
        )
        and (filters.method is None or report.method == filters.method)
    ]
    return {"count": len(records), "next": None, "previous": None, "results": records}


async def job_status(filters: TaskFilters) -> JsonValue:
    """Summarize visible historical reports, not all users or page completion."""
    _ = await invoke("GET", f"documents/{filters.document_id}/")
    if filters.group_id is not None:
        _ = await invoke(
            "GET",
            f"documents/{filters.document_id}/task_groups/{filters.group_id}/",
        )
    reports = task_records(await read_tasks(filters))
    tally = Counter(report.workflow_state for report in reports)
    counts: dict[str, JsonValue] = {
        label: tally[state] for state, label in enumerate(STATE_NAMES)
    }
    counts["unknown"] = sum(
        count for state, count in tally.items() if state not in range(len(STATE_NAMES))
    )
    total = len(reports)
    terminal = tally[2] + tally[3] + tally[4]
    return {
        "scope": "current_user_task_reports",
        "document_id": filters.document_id,
        "group_id": filters.group_id,
        "method": filters.method,
        "counts": counts,
        "total": total,
        "terminal_count": terminal,
        "terminal_percent": round(100 * terminal / total, 2) if total else None,
        "all_finished": total > 0 and tally[3] == total,
        "has_failures": tally[2] > 0,
        "has_active": tally[0] + tally[1] > 0,
        "reports": [report.as_json() for report in reports],
        "limitations": (
            "Only reports visible to the authenticated user are included. "
            "Ungrouped summaries include historical jobs. Terminal counts include "
            "failures and cancellations; they are not success or page percentages. "
            "Running-job progress and import processed/total counts are unavailable. "
            "Pagination is not an atomic snapshot; refresh while jobs are changing."
        ),
    }
