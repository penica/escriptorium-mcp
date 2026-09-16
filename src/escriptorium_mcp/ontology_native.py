"""Discover version-dependent ontology features and use native file endpoints."""

from pathlib import Path
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field, FilePath, JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, Input, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.ontology_models import TypeKind

Scope = Literal["documents", "projects"]
Color = Annotated[str, Field(max_length=7)]


class NativeRequest(Input):
    """Private native operation with paths interpreted on the MCP host."""

    operation: Literal["ontology_native"] = "ontology_native"
    action: Literal["capabilities", "export", "import"]
    scope: Scope
    resource_id: Identifier
    file_path: FilePath | None = None
    destination: Path | None = None


class FieldInfo(BaseModel):
    """Writable field evidence from the DRF OPTIONS response."""

    read_only: bool = False


class Options(BaseModel):
    """Only action field metadata is needed for optional color support."""

    actions: dict[str, dict[str, FieldInfo]] = Field(default_factory=dict)


class EndpointEvidence(BaseModel):
    """Typed action permissions from the worker's OPTIONS probe."""

    status: str
    http_status: int
    methods: list[str]


class Capabilities(BaseModel):
    """Typed endpoint availability for guarded project actions."""

    endpoints: dict[str, EndpointEvidence]


async def require_project_action(project_id: int, method: str) -> None:
    """Separate inaccessible parents from absent or denied template actions."""
    capabilities = Capabilities.model_validate(
        await call(
            NativeRequest(
                action="capabilities",
                scope="projects",
                resource_id=project_id,
            )
        )
    )
    endpoint = capabilities.endpoints["ontology"]
    if endpoint.status != "available" or method not in endpoint.methods:
        msg = (
            f"Project ontology action {method} is unavailable: "
            f"{endpoint.status} (HTTP {endpoint.http_status})."
        )
        raise ToolError(msg)


class ColorChange(Input):
    """Native seven-character color field; blank/null clears the override."""

    color: Color | None


async def supports_type_color(kind: TypeKind) -> bool:
    """Detect optional fields before writes; older APIs silently ignore extras."""
    options = Options.model_validate(
        await call(ApiRequest(method="OPTIONS", route=f"types/{kind}/"))
    )
    return any(
        "color" in fields and not fields["color"].read_only
        for fields in options.actions.values()
    )


def register_native(server: MCPServer) -> None:
    """Expose modern endpoints without claiming they exist on older servers."""

    @server.tool(annotations=READ)
    async def get_ontology_capabilities(
        scope: Scope, resource_id: Identifier
    ) -> JsonValue:
        """Probe native import/export and project templates using GET and OPTIONS.

        A missing/denied parent stays an HTTP error. Endpoint 404 means absent
        or hidden, 403 means denied; neither is guessed to be a server version.
        Methods and serializer fields are reported where OPTIONS supplies them.
        """
        return await call(
            NativeRequest(action="capabilities", scope=scope, resource_id=resource_id)
        )

    @server.tool(annotations=CREATE)
    async def export_native_ontology(
        scope: Scope, resource_id: Identifier, destination: Path
    ) -> JsonValue:
        """Save native ontology YAML on the MCP host without overwriting files.

        Requires the server's native endpoint; use portable ontology backup on
        older servers. Project export can return 404 when no template is set.
        """
        return await call(
            NativeRequest(
                action="export",
                scope=scope,
                resource_id=resource_id,
                destination=destination,
            )
        )

    @server.tool(annotations=CHANGE)
    async def import_native_ontology(
        scope: Scope, resource_id: Identifier, file_path: FilePath
    ) -> JsonValue:
        """Apply server-native YAML/legacy JSON from the MCP host (maximum 16 MiB).

        Document import can replace definitions and affect annotations; project
        import sets the template for future documents. Preserve returned warnings.
        Unsupported/denied endpoints return capability evidence without writing.
        """
        return await call(
            NativeRequest(
                action="import",
                scope=scope,
                resource_id=resource_id,
                file_path=file_path,
            )
        )

    @server.tool(annotations=READ)
    async def get_project_ontology(project_id: Identifier) -> JsonValue:
        """Read the default template for future documents; null means none set.

        Older servers return 404 for the unsupported endpoint.
        """
        await require_project_action(project_id, "GET")
        return await invoke("GET", f"projects/{project_id}/ontology/")

    @server.tool(annotations=DELETE)
    async def delete_project_ontology(project_id: Identifier) -> JsonValue:
        """Clear the project template without changing existing documents."""
        await require_project_action(project_id, "DELETE")
        return await invoke("DELETE", f"projects/{project_id}/ontology/")

    @server.tool(annotations=READ)
    async def get_ontology_type(kind: TypeKind, type_id: Identifier) -> JsonValue:
        """Read a public/template type; private document types may return 404.

        Use get_document_ontology for assigned document-owned type records.
        """
        return await invoke("GET", f"types/{kind}/{type_id}/")

    @server.tool(annotations=CHANGE)
    async def update_ontology_type_color(
        kind: TypeKind, type_id: Identifier, color: Color | None
    ) -> JsonValue:
        """Set a region/line type color when exposed by this server's OPTIONS.

        Prefer #RRGGBB; blank or null clears the override. Permission rules
        still apply; public templates may be read-only.
        """
        if not await supports_type_color(kind):
            msg = "This server does not expose a writable color field for this type."
            raise ToolError(msg)
        return await invoke(
            "PATCH", f"types/{kind}/{type_id}/", ColorChange(color=color)
        )
