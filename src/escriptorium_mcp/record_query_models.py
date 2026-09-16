"""Native project/document filters, statistics and typed page lookups."""

from typing import Annotated, Literal

from pydantic import Field

from escriptorium_mcp.api import Input
from escriptorium_mcp.bridge import Identifier

TagExpression = Annotated[
    str,
    Field(
        pattern=(
            r"^(?:none|[1-9][0-9]*(?:,[1-9][0-9]*)*|"
            r"(?:none|[1-9][0-9]*)(?:\|(?:none|[1-9][0-9]*))+)$"
        )
    ),
]
ProjectOrdering = Literal[
    "created_at",
    "-created_at",
    "documents_count",
    "-documents_count",
    "id",
    "-id",
    "name",
    "-name",
    "owner",
    "-owner",
    "updated_at",
    "-updated_at",
]
DocumentOrdering = Literal[
    "name",
    "-name",
    "parts_count",
    "-parts_count",
    "updated_at",
    "-updated_at",
]


class RecordFilters(Input):
    """Name substring and tag IDs joined by comma (all) or pipe (any).

    The token none selects untagged records, alone or in a pipe expression.
    Native OR results may contain duplicate records; counts are preserved.
    """

    name: str | None = None
    tags: TagExpression | None = None


class ProjectFilters(RecordFilters):
    """Project ordering whitelist; omitted ordering uses the server default."""

    ordering: Annotated[list[ProjectOrdering], Field(min_length=1)] | None = None


class DocumentFilters(RecordFilters):
    """Filter by numeric project ID; document writes instead use project slugs."""

    project: Identifier | None = None
    ordering: Annotated[list[DocumentOrdering], Field(min_length=1)] | None = None


class StatisticsOptions(Input):
    """Default statistics can be cached for one hour; refresh updates that cache."""

    ordering: (
        Literal[
            "frequency",
            "-frequency",
            "typology",
            "-typology",
            "taxonomy",
            "-taxonomy",
        ]
        | None
    ) = None
    refresh: bool = False


class ElementQuery(Input):
    """Find pages containing a type, or none for untyped elements."""

    category: Literal["regions", "lines", "text", "image"]
    type_id: Identifier | Literal["none"]
