"""Best-effort task-group reads shared by accepted job submissions."""

from typing import ClassVar, assert_never

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import Identifier, call


class SubmissionGroup(BaseModel):
    """Keep unknown group fields; a missing method cannot establish attribution."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    pk: Identifier
    method: str | None = None

    def as_json(self) -> JsonValue:
        """Retain the server's group fields without adding absent optional fields."""
        return TypeAdapter[JsonValue](JsonValue).validate_json(
            self.model_dump_json(exclude_unset=True)
        )


class SubmissionGroupPage(BaseModel):
    """Parse the paginated response after the adapter has followed next links."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    results: list[SubmissionGroup]


async def read_submission_groups(
    document_id: Identifier,
) -> list[SubmissionGroup] | None:
    """Keep optional monitoring failures from turning accepted writes into retries."""
    try:
        raw = await call(
            ApiRequest(
                method="GET",
                route=f"documents/{document_id}/task_groups/",
                paginate=True,
            )
        )
        parsed = TypeAdapter[list[SubmissionGroup] | SubmissionGroupPage](
            list[SubmissionGroup] | SubmissionGroupPage
        ).validate_python(raw)
    except (ToolError, ValidationError):
        return None
    match parsed:
        case SubmissionGroupPage(results=groups):
            return groups
        case list():
            return parsed
        case _:
            assert_never(parsed)
