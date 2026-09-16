"""Read before writing partial taxonomy definitions with replacement relations."""

from typing import Annotated

from mcp.server import MCPServer
from pydantic import BaseModel, Field, JsonValue

from escriptorium_mcp.annotation_models import (
    AnnotationTaxonomy,
    AnnotationType,
    MarkerType,
)
from escriptorium_mcp.api import CHANGE, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.record_models import Patch


class ComponentReference(BaseModel):
    """Expanded component reference returned by the API."""

    pk: Identifier


class ComponentType(BaseModel):
    """Global type with additional response fields ignored."""

    name: str


class TaxonomyState(BaseModel):
    """Complete editable definition as returned by eScriptorium."""

    pk: Identifier
    name: str
    marker_type: MarkerType
    abbreviation: str | None
    marker_detail: str | None
    has_comments: bool
    typology: ComponentType | None
    components: list[ComponentReference | Identifier]

    def definition(self) -> AnnotationTaxonomy:
        """Normalize expanded relations to the accepted write representation."""
        return AnnotationTaxonomy(
            name=self.name,
            marker_type=self.marker_type,
            abbreviation=self.abbreviation,
            marker_detail=self.marker_detail,
            has_comments=self.has_comments,
            typology=AnnotationType(name=self.typology.name) if self.typology else None,
            components=[
                ref.pk if isinstance(ref, ComponentReference) else ref
                for ref in self.components
            ],
        )


class TaxonomyPatch(Patch):
    """Only supplied fields change; null typology clears the relation."""

    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"\S")] = ""
    marker_type: MarkerType = "Rectangle"
    abbreviation: Annotated[str, Field(max_length=3)] | None = ""
    marker_detail: Annotated[str, Field(max_length=7)] | None = ""
    has_comments: bool = False
    typology: AnnotationType | None = None
    components: list[Identifier] = Field(default_factory=list)


async def patch_taxonomy(
    document_id: int,
    taxonomy_id: int,
    changes: TaxonomyPatch,
) -> JsonValue:
    """Preserve omitted fields despite the upstream relation replacement behavior."""
    route = f"documents/{document_id}/taxonomies/annotations/{taxonomy_id}/"
    state = TaxonomyState.model_validate(
        await call(ApiRequest(method="GET", route=route))
    )
    merged = state.definition().model_dump()
    merged.update(changes.model_dump(exclude_unset=True))
    definition = AnnotationTaxonomy.model_validate(merged)
    return await call(
        ApiRequest(
            method="PATCH",
            route=route,
            body_json=definition.model_dump_json(
                exclude={"typology"} if definition.typology is None else set(),
            ),
        )
    )


def register_taxonomy_edits(server: MCPServer) -> None:
    """Register a relation-preserving alternative to full taxonomy replacement."""

    @server.tool(annotations=CHANGE)
    async def patch_annotation_taxonomy(
        document_id: Identifier,
        taxonomy_id: Identifier,
        changes: TaxonomyPatch,
    ) -> JsonValue:
        """Edit only supplied taxonomy fields, preserving omitted relations/settings.

        Explicit typology=null clears its relation; components=[] removes all fields.
        The API has no atomic conditional update: avoid concurrent taxonomy edits.
        """
        return await patch_taxonomy(document_id, taxonomy_id, changes)
