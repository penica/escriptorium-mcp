"""Typed inventories for safe annotation taxonomy migration."""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.taxonomy_edit import ComponentReference, TaxonomyState


class StoredValue(BaseModel):
    """Existing annotation value, including its component relation."""

    component: ComponentReference | Identifier
    value: str | None

    def component_id(self) -> int:
        """Normalize expanded component references."""
        return (
            self.component.pk
            if isinstance(self.component, ComponentReference)
            else self.component
        )


class AnnotationState(BaseModel):
    """Retain all annotation fields for optimistic conflict checks."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")
    pk: Identifier
    taxonomy: Identifier
    components: list[StoredValue]


class AnnotationAddress(BaseModel):
    """Address and complete original contents of an annotation."""

    route: str
    kind: Literal["image", "text"]
    original: AnnotationState


class AnnotationPage(BaseModel):
    """An annotation collection after following every pagination link."""

    results: list[AnnotationState]


class PartsPage(BaseModel):
    """Page references without requiring unrelated page metadata."""

    results: list[ComponentReference]


class MigrationPatch(BaseModel):
    """Empty component updates preserve existing upstream values."""

    taxonomy: Identifier
    components: list[JsonValue] = Field(default_factory=list)


async def read_taxonomy(document_id: int, taxonomy_id: int) -> TaxonomyState:
    """Read a scoped annotation category."""
    route = f"documents/{document_id}/taxonomies/annotations/{taxonomy_id}/"
    return TaxonomyState.model_validate(
        await call(ApiRequest(method="GET", route=route))
    )


async def annotations(document_id: int, taxonomy_id: int) -> list[AnnotationAddress]:
    """Inventory both annotation kinds on every page, including plain lists."""
    root = f"documents/{document_id}/parts/"
    raw = await call(ApiRequest(method="GET", route=root, paginate=True))
    pages = TypeAdapter[list[ComponentReference] | PartsPage](
        list[ComponentReference] | PartsPage
    ).validate_python(raw)
    parts = pages.results if isinstance(pages, PartsPage) else pages
    result: list[AnnotationAddress] = []
    kinds: tuple[Literal["image", "text"], ...] = ("image", "text")
    for part in parts:
        for kind in kinds:
            route = f"{root}{part.pk}/annotations/{kind}/"
            raw = await call(ApiRequest(method="GET", route=route, paginate=True))
            parsed = TypeAdapter[list[AnnotationState] | AnnotationPage](
                list[AnnotationState] | AnnotationPage
            ).validate_python(raw)
            records = parsed.results if isinstance(parsed, AnnotationPage) else parsed
            result.extend(
                AnnotationAddress(route=f"{route}{row.pk}/", kind=kind, original=row)
                for row in records
                if row.taxonomy == taxonomy_id
            )
    return result
