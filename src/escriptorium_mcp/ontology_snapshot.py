"""Read portable ontology snapshots without copying annotation instances."""

from typing import Generic, TypeVar

from pydantic import BaseModel, TypeAdapter

from escriptorium_mcp.annotation_models import AnnotationComponent, AnnotationTaxonomy
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.ontology_models import OntologyType
from escriptorium_mcp.ontology_snapshot_models import (
    OntologySnapshot,
    SnapshotTaxonomy,
    SnapshotType,
)
from escriptorium_mcp.ontology_tools import read_ontology

Item = TypeVar("Item")


class Collection(BaseModel, Generic[Item]):
    """Worker preserves the pagination envelope after collecting every page."""

    results: list[Item]


class ComponentRead(BaseModel):
    """Server component, allowing additional response metadata."""

    pk: Identifier
    name: str
    allowed_values: list[str] | None


class TaxonomyRead(BaseModel):
    """Nested serializer relations alongside the complete display definition."""

    pk: Identifier
    name: str
    marker_type: str
    abbreviation: str | None = ""
    marker_detail: str | None = ""
    has_comments: bool = False
    typology: OntologyType | None = None
    components: list[ComponentRead]

    def portable(self) -> SnapshotTaxonomy:
        """Drop IDs and retain relation names for cross-server restoration."""
        return SnapshotTaxonomy.model_validate(
            {
                **self.model_dump(exclude={"pk", "typology", "components"}),
                "typology": self.typology.name if self.typology else None,
                "components": [item.name for item in self.components],
            }
        )


async def read_components(document_id: int) -> list[ComponentRead]:
    """Read every component including unused fields."""
    parsed = TypeAdapter[list[ComponentRead] | Collection[ComponentRead]](
        list[ComponentRead] | Collection[ComponentRead]
    ).validate_python(
        await call(
            ApiRequest(
                method="GET",
                route=f"documents/{document_id}/taxonomies/components/",
                paginate=True,
            )
        )
    )

    return parsed.results if isinstance(parsed, Collection) else parsed


async def read_taxonomies(document_id: int) -> list[TaxonomyRead]:
    """Read every annotation schema with its nested field references."""
    parsed = TypeAdapter[list[TaxonomyRead] | Collection[TaxonomyRead]](
        list[TaxonomyRead] | Collection[TaxonomyRead]
    ).validate_python(
        await call(
            ApiRequest(
                method="GET",
                route=f"documents/{document_id}/taxonomies/annotations/",
                paginate=True,
            )
        )
    )

    return parsed.results if isinstance(parsed, Collection) else parsed


async def export_snapshot(document_id: int) -> OntologySnapshot:
    """Capture portable definitions, refusing ambiguous or broken references."""
    ontology = await read_ontology(document_id)
    return OntologySnapshot(
        valid_block_types=[
            SnapshotType(name=t.name, color=t.color) for t in ontology.valid_block_types
        ],
        valid_line_types=[
            SnapshotType(name=t.name, color=t.color) for t in ontology.valid_line_types
        ],
        valid_part_types=[
            SnapshotType(name=t.name, color=t.color) for t in ontology.valid_part_types
        ],
        components=[
            AnnotationComponent(name=c.name, allowed_values=c.allowed_values)
            for c in await read_components(document_id)
        ],
        taxonomies=[t.portable() for t in await read_taxonomies(document_id)],
    )


def taxonomy_payload(
    taxonomy: SnapshotTaxonomy,
    components: list[ComponentRead],
) -> AnnotationTaxonomy:
    """Resolve portable component references using destination document IDs."""
    ids = {item.name: item.pk for item in components}
    return AnnotationTaxonomy.model_validate(
        {
            **taxonomy.model_dump(exclude={"components", "typology"}),
            "components": [ids[name] for name in taxonomy.components],
            "typology": {"name": taxonomy.typology} if taxonomy.typology else None,
        }
    )
