from dataclasses import dataclass, field

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, TypeAdapter

from escriptorium_mcp.annotation_models import AnnotationComponent, AnnotationTaxonomy
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.ontology_models import DocumentOntology, OntologyType
from escriptorium_mcp.ontology_snapshot import ComponentRead, TaxonomyRead
from escriptorium_mcp.ontology_snapshot_models import SnapshotType


@dataclass(slots=True)
class SnapshotAPI:
    document: DocumentOntology = field(
        default_factory=lambda: DocumentOntology(
            valid_block_types=[], valid_line_types=[], valid_part_types=[]
        )
    )
    components: list[ComponentRead] = field(default_factory=list)
    taxonomies: list[TaxonomyRead] = field(default_factory=list)
    writes: list[ApiRequest] = field(default_factory=list)
    fail_taxonomy: bool = False

    async def request(self, request: ApiRequest) -> JsonValue:
        route = request.route
        if request.method == "GET":
            return self.read(route)
        self.writes.append(request)
        if route.startswith("types/"):
            definition = SnapshotType.model_validate_json(request.body_json)
            return {"pk": 7, "name": definition.name, "color": definition.color}
        if route.endswith("/modify_ontology/"):
            selection = TypeAdapter(dict[str, list[int]]).validate_json(
                request.body_json
            )
            assert selection == {"valid_block_types": [7]}
            self.document = DocumentOntology(
                valid_block_types=[OntologyType(pk=107, name="Body")],
                valid_line_types=[],
                valid_part_types=[],
            )
            return self.document.model_dump(mode="json")
        if route.endswith("/components/"):
            component = AnnotationComponent.model_validate_json(request.body_json)
            created = ComponentRead(
                pk=209, name=component.name, allowed_values=component.allowed_values
            )
            self.components.append(created)
            return created.model_dump(mode="json")
        if route.endswith("/annotations/"):
            if self.fail_taxonomy:
                msg = "Fixture taxonomy failure"
                raise ToolError(msg)
            taxonomy = AnnotationTaxonomy.model_validate_json(request.body_json)
            assert taxonomy.components == [209]
            created_taxonomy = TaxonomyRead.model_validate(
                {
                    **taxonomy.model_dump(exclude={"components", "typology"}),
                    "pk": 309,
                    "components": [item.model_dump() for item in self.components],
                    "typology": {"pk": 409, "name": taxonomy.typology.name}
                    if taxonomy.typology
                    else None,
                }
            )
            self.taxonomies.append(created_taxonomy)
            return created_taxonomy.model_dump(mode="json")
        msg = f"Unexpected fixture route {route}"
        raise AssertionError(msg)

    def read(self, route: str) -> JsonValue:
        if route.endswith("/components/"):
            return [item.model_dump(mode="json") for item in self.components]
        if route.endswith("/annotations/"):
            return [item.model_dump(mode="json") for item in self.taxonomies]
        return self.document.model_dump(mode="json")
