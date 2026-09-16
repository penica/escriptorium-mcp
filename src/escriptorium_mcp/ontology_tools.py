"""Type definition and document ontology management."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.ontology_models import (
    ContentKind,
    DocumentOntology,
    OntologySelection,
    OntologyType,
    TypeDefinition,
    TypeKind,
)
from escriptorium_mcp.ontology_native import supports_type_color
from escriptorium_mcp.pagination import PageSelection, paginated_request


async def read_ontology(document_id: int) -> DocumentOntology:
    """Use the raw document API; the legacy connector drops newer metadata."""
    return DocumentOntology.model_validate(
        await invoke("GET", f"documents/{document_id}/")
    )


def selection(kind: ContentKind, ids: list[int]) -> OntologySelection:
    """Build a single-category replacement without clearing other lists."""
    return OntologySelection.model_validate({f"valid_{kind}_types": ids})


async def check_color(kind: TypeKind, data: TypeDefinition) -> None:
    """Reject unsupported optional fields instead of allowing silent API drops."""
    if "color" in data.model_fields_set and not await supports_type_color(kind):
        msg = "This server does not expose a writable color field for this type."
        raise ToolError(msg)


def register_ontology(server: MCPServer) -> None:
    """Expose the ontology operations available on the installed API."""

    @server.tool(annotations=READ)
    async def get_document_ontology(document_id: Identifier) -> JsonValue:
        """Read the document's allowed page, region and line types with actual IDs."""
        return (await read_ontology(document_id)).model_dump(
            mode="json", exclude_none=True
        )

    @server.tool(annotations=READ)
    async def list_ontology_types(
        kind: TypeKind,
        pagination: PageSelection | None = None,
    ) -> JsonValue:
        """List public/template types, optionally selecting one fixed-size page."""
        route = f"types/{kind}/"
        return await call(
            paginated_request(route, pagination, page_size_supported=False)
            if pagination is not None
            else ApiRequest(method="GET", route=route, paginate=True)
        )

    @server.tool(annotations=CREATE)
    async def create_ontology_type(kind: TypeKind, data: TypeDefinition) -> JsonValue:
        """Create/reuse a named type; this does not attach it to a document."""
        await check_color(kind, data)
        return await invoke("POST", f"types/{kind}/", data)

    @server.tool(annotations=CHANGE)
    async def update_ontology_type(
        kind: TypeKind,
        type_id: Identifier,
        changes: TypeDefinition,
    ) -> JsonValue:
        """Rename a type. Legacy/shared types affect every document using that ID."""
        await check_color(kind, changes)
        return await invoke("PATCH", f"types/{kind}/{type_id}/", changes)

    @server.tool(annotations=DELETE)
    async def delete_ontology_type(kind: TypeKind, type_id: Identifier) -> JsonValue:
        """Delete a definition globally where permitted.

        Page/region/line references become untyped. Deleting an annotation
        type can cascade to taxonomies and their annotations.

        To remove it only from one document, use set_document_ontology instead.
        """
        return await invoke("DELETE", f"types/{kind}/{type_id}/")

    @server.tool(annotations=CHANGE)
    async def set_document_ontology(
        document_id: Identifier,
        types: OntologySelection,
    ) -> JsonValue:
        """Replace supplied allowed-type lists, preserving omitted categories.

        Audit/reassign used types before removal. Newer servers may clear content
        assignments when dropping a document-owned type. Re-read resulting IDs.
        """
        return await invoke("PATCH", f"documents/{document_id}/modify_ontology/", types)

    @server.tool(annotations=CREATE)
    async def add_document_ontology_type(
        document_id: Identifier,
        kind: ContentKind,
        data: TypeDefinition,
    ) -> JsonValue:
        """Create/reuse and attach a named type while keeping existing allowed types.

        Multiple requests are not atomic. If attachment fails, the created
        definition may remain. Re-read the document to obtain its assigned ID.
        """
        await check_color(kind, data)
        ontology = await read_ontology(document_id)
        existing = next(
            (item for item in ontology.types(kind) if item.name == data.name), None
        )
        if existing is not None:
            if "color" in data.model_fields_set and data.color != existing.color:
                msg = (
                    "This name already exists with another color; "
                    "update its ID explicitly."
                )
                raise ToolError(msg)
            return ontology.model_dump(mode="json", exclude_none=True)
        created = OntologyType.model_validate(
            await invoke("POST", f"types/{kind}/", data)
        )
        latest = await read_ontology(document_id)
        ids = list(
            dict.fromkeys([item.pk for item in latest.types(kind)] + [created.pk])
        )
        _ = await invoke(
            "PATCH", f"documents/{document_id}/modify_ontology/", selection(kind, ids)
        )
        return (await read_ontology(document_id)).model_dump(
            mode="json", exclude_none=True
        )
