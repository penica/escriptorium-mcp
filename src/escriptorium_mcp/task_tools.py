"""Task groups, document summaries, import monitoring and cancellation."""

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.task_monitoring import (
    IMPORT_METHOD,
    StateLabel,
    TaskFilters,
    job_status,
)


def register_task_monitoring(server: MCPServer) -> None:
    """Expose reporting actions without modifying task-history records."""

    @server.tool(annotations=READ)
    async def list_document_tasks(
        name: str | None = None,
        task_state: StateLabel | None = None,
        user_id: Identifier | None = None,
    ) -> JsonValue:
        """List document task counts and last-start timestamps, following pagination.

        Name matches a substring. State selects documents with that state; counts
        still include their historical reports in every state. user_id is for
        staff only; nonstaff results follow the server's document ownership rules.
        """
        query = {
            key: str(value)
            for key, value in (
                ("name", name),
                ("task_state", task_state),
                ("user_id", user_id),
            )
            if value is not None
        }
        return await call(
            ApiRequest(
                method="GET", route="documents/tasks/", paginate=True, query=query
            )
        )

    @server.tool(annotations=READ)
    async def list_task_groups(document_id: Identifier) -> JsonValue:
        """List all document job groups with state counts and affected-page counts."""
        return await call(
            ApiRequest(
                method="GET",
                route=f"documents/{document_id}/task_groups/",
                paginate=True,
            )
        )

    @server.tool(annotations=READ)
    async def get_task_group(
        document_id: Identifier, group_id: Identifier
    ) -> JsonValue:
        """Read group state buckets, counts and timestamps; inspect every bucket.

        A bucket's done_at is its latest report finish, not proof the group
        succeeded. page_count counts associated pages, not completed pages.
        """
        return await invoke("GET", f"documents/{document_id}/task_groups/{group_id}/")

    @server.tool(annotations=READ)
    async def get_document_job_status(
        document_id: Identifier, group_id: Identifier | None = None
    ) -> JsonValue:
        """Summarize the current user's task reports, including failure messages.

        Filter by group to monitor one submission. Without a group, historical
        jobs are included. terminal_percent includes failures/cancellations and
        is not page progress. Empty/unknown reports never mean successful completion.
        """
        return await job_status(TaskFilters(document_id=document_id, group_id=group_id))

    @server.tool(annotations=READ)
    async def get_import_status(
        document_id: Identifier, group_id: Identifier | None = None
    ) -> JsonValue:
        """Read visible import task history, messages and report state counts.

        Filter by group to narrow reports; without it old imports are included.
        Inspect timestamps and messages, including skipped-file warnings. A finished
        import report does not prove separately queued image conversion is finished.
        No visible reports does not prove no import exists. Native import record
        status, processed/total counts and progress percentages are not exposed.
        """
        return await job_status(
            TaskFilters(
                document_id=document_id, group_id=group_id, method=IMPORT_METHOD
            )
        )

    @server.tool(annotations=CHANGE)
    async def cancel_document_tasks(document_id: Identifier) -> JsonValue:
        """Cancel all queued/running document tasks and mark training/imports canceled.

        Requires owner/staff permission. The upstream operation is not atomic;
        refresh reports afterward. This is document-wide, across users and pages.
        """
        return await invoke("POST", f"documents/{document_id}/cancel_tasks/")

    @server.tool(annotations=CHANGE)
    async def cancel_document_import(document_id: Identifier) -> JsonValue:
        """Cancel the latest document import through its dedicated server action.

        This cannot select an arbitrary historical import. Already stopped imports
        return an upstream error; some versions return HTTP 500 when none exists.
        Task history alone cannot reliably prove that a cancelable import exists.
        Latest is selected when the action runs, so concurrent imports can change
        its target. Cancellation before report attachment may not stop a queued
        task; existing image/text changes are not rolled back.
        """
        return await invoke("POST", f"documents/{document_id}/cancel_import/")
