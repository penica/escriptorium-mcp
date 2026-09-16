"""Complete, paginated inventories of ontology assignments."""

from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, JsonValue, TypeAdapter

from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.bridge import call
from escriptorium_mcp.ontology_models import ContentKind, OntologyType
from escriptorium_mcp.ontology_tools import read_ontology


class Element(BaseModel):
    """Require a typology field so incomplete responses cannot mean unassigned."""

    pk: int
    typology: int | OntologyType | None

    def type_id(self) -> int | None:
        """Normalize API versions returning expanded or numeric type references."""
        if isinstance(self.typology, OntologyType):
            return self.typology.pk
        return self.typology


class ElementPage(BaseModel):
    """Paginated result after the bridge follows every next link."""

    results: list[Element]


class Assignment(BaseModel):
    """Address of content with its current classification."""

    kind: ContentKind
    page_id: int
    element_id: int
    type_id: int | None
    route: str


async def elements(route: str) -> list[Element]:
    """Read either a plain list or a paginated endpoint without truncation."""
    value = TypeAdapter[list[Element] | ElementPage](
        list[Element] | ElementPage
    ).validate_python(await call(ApiRequest(method="GET", route=route, paginate=True)))
    return value.results if isinstance(value, ElementPage) else value


async def inventory(
    document_id: int,
    kind: ContentKind | Literal["all"] = "all",
) -> list[Assignment]:
    """Read every page, plus requested region/line assignments."""
    root = f"documents/{document_id}/parts/"
    assignments: list[Assignment] = []
    for page in await elements(root):
        if kind in {"part", "all"}:
            assignments.append(
                Assignment(
                    kind="part",
                    page_id=page.pk,
                    element_id=page.pk,
                    type_id=page.type_id(),
                    route=f"{root}{page.pk}/",
                )
            )
        categories: tuple[tuple[ContentKind, str], ...] = (
            ("block", "blocks"),
            ("line", "lines"),
        )
        for category, suffix in categories:
            if kind not in {category, "all"}:
                continue
            path = f"{root}{page.pk}/{suffix}/"
            assignments.extend(
                Assignment(
                    kind=category,
                    page_id=page.pk,
                    element_id=item.pk,
                    type_id=item.type_id(),
                    route=f"{path}{item.pk}/",
                )
                for item in await elements(path)
            )
    return assignments


async def audit(document_id: int) -> JsonValue:
    """Identify duplicate labels, unused definitions and invalid assignments."""
    ontology = await read_ontology(document_id)
    records = await inventory(document_id)
    report: dict[str, JsonValue] = {"document_id": document_id}
    for kind in ("part", "block", "line"):
        types = ontology.types(kind)
        ids = {item.pk for item in types}
        rows = [item for item in records if item.kind == kind]
        counts = Counter(item.type_id for item in rows)
        names: dict[str, list[int]] = defaultdict(list)
        for item in types:
            names[item.name.strip().casefold()].append(item.pk)
        report[kind] = {
            "total": len(rows),
            "untyped": counts[None],
            "types": [
                {"pk": item.pk, "name": item.name, "uses": counts[item.pk]}
                for item in types
            ],
            "duplicate_labels": [
                list(values) for values in names.values() if len(values) > 1
            ],
            "outside_ontology": [
                item.model_dump(mode="json")
                for item in rows
                if item.type_id is not None and item.type_id not in ids
            ],
        }
    return report
