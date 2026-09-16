"""Document-scoped annotation components and taxonomies."""

from typing import Literal

from mcp.server import MCPServer
from pydantic import JsonValue

from escriptorium_mcp.annotation_models import (
    AnnotationComponent,
    AnnotationComponentPatch,
    AnnotationTaxonomy,
    AnnotationTaxonomyReplacement,
)
from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.pagination import PageSelection, paginated_request


def register_annotations(server: MCPServer) -> None:
    """Register annotation ontology definitions, independently of annotation data."""

    @server.tool(annotations=READ)
    async def list_annotation_components(
        document_id: Identifier,
        pagination: PageSelection | None = None,
    ) -> JsonValue:
        """List annotation input fields; opt-in pages may request page_size."""
        route = f"documents/{document_id}/taxonomies/components/"
        return await call(
            paginated_request(route, pagination, page_size_supported=True)
            if pagination is not None
            else ApiRequest(
                method="GET",
                paginate=True,
                route=route,
            )
        )

    @server.tool(annotations=READ)
    async def get_annotation_component(
        document_id: Identifier,
        component_id: Identifier,
    ) -> JsonValue:
        """Read an annotation input field and its allowed values."""
        return await invoke(
            "GET", f"documents/{document_id}/taxonomies/components/{component_id}/"
        )

    @server.tool(annotations=CREATE)
    async def create_annotation_component(
        document_id: Identifier,
        component: AnnotationComponent,
    ) -> JsonValue:
        """Create a document annotation field; empty allowed_values means free text."""
        return await invoke(
            "POST", f"documents/{document_id}/taxonomies/components/", component
        )

    @server.tool(annotations=CHANGE)
    async def update_annotation_component(
        document_id: Identifier,
        component_id: Identifier,
        changes: AnnotationComponentPatch,
    ) -> JsonValue:
        """Rename a field or replace its allowed values; annotation text remains."""
        return await invoke(
            "PATCH",
            f"documents/{document_id}/taxonomies/components/{component_id}/",
            changes,
        )

    @server.tool(annotations=DELETE)
    async def delete_annotation_component(
        document_id: Identifier,
        component_id: Identifier,
    ) -> JsonValue:
        """Delete an annotation field; associated annotation values may be deleted."""
        return await invoke(
            "DELETE", f"documents/{document_id}/taxonomies/components/{component_id}/"
        )

    @server.tool(annotations=READ)
    async def list_annotation_taxonomies(
        document_id: Identifier,
        target: Literal["image", "text"] | None = None,
        pagination: PageSelection | None = None,
    ) -> JsonValue:
        """List categories by target or native page, with optional page_size."""
        route = f"documents/{document_id}/taxonomies/annotations/"
        query = {"target": target} if target else {}
        return await call(
            paginated_request(
                route,
                pagination,
                query=query,
                page_size_supported=True,
            )
            if pagination is not None
            else ApiRequest(
                method="GET",
                paginate=True,
                route=route,
                query=query,
            )
        )

    @server.tool(annotations=READ)
    async def get_annotation_taxonomy(
        document_id: Identifier,
        taxonomy_id: Identifier,
    ) -> JsonValue:
        """Read a complete annotation category before replacing its definition."""
        return await invoke(
            "GET", f"documents/{document_id}/taxonomies/annotations/{taxonomy_id}/"
        )

    @server.tool(annotations=CREATE)
    async def create_annotation_taxonomy(
        document_id: Identifier,
        taxonomy: AnnotationTaxonomy,
    ) -> JsonValue:
        """Create an annotation category; typology uses name, components use IDs."""
        return await call(
            ApiRequest(
                method="POST",
                route=f"documents/{document_id}/taxonomies/annotations/",
                body_json=taxonomy.model_dump_json(
                    exclude={"typology"} if taxonomy.typology is None else set()
                ),
            )
        )

    @server.tool(annotations=CHANGE)
    async def update_annotation_taxonomy(
        document_id: Identifier,
        taxonomy_id: Identifier,
        definition: AnnotationTaxonomyReplacement,
    ) -> JsonValue:
        """Replace the full definition: supply every setting to preserve it.

        Read first; convert nested components to their IDs and typology to {name}.
        Explicit components=[] removes all fields; typology=null clears the type.
        Omitted display fields reset to defaults. Existing annotations remain.
        """
        return await call(
            ApiRequest(
                method="PATCH",
                route=f"documents/{document_id}/taxonomies/annotations/{taxonomy_id}/",
                body_json=definition.model_dump_json(
                    exclude={"typology"} if definition.typology is None else set()
                ),
            )
        )

    @server.tool(annotations=DELETE)
    async def delete_annotation_taxonomy(
        document_id: Identifier,
        taxonomy_id: Identifier,
    ) -> JsonValue:
        """Delete an annotation category; its existing annotations may be deleted."""
        return await invoke(
            "DELETE", f"documents/{document_id}/taxonomies/annotations/{taxonomy_id}/"
        )
