"""CRUD for image and text annotation instances, including W3C representations."""

import json

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import CHANGE, CREATE, DELETE, READ, ApiRequest, invoke
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.instance_models import (
    AnnotationKind,
    AnnotationTarget,
    AnnotationValues,
    ImageAnnotationCreate,
    ImageAnnotationPatch,
    TextAnnotationCreate,
    TextAnnotationPatch,
)
from escriptorium_mcp.pagination import PageSelection, paginated_request


async def write_annotation(
    route: str,
    data: AnnotationValues,
    *,
    page_id: Identifier | None = None,
) -> JsonValue:
    """Include required components and derive creation's part from its route input."""
    payload = data.model_dump(mode="json", exclude_unset=True)
    payload["components"] = [value.model_dump(mode="json") for value in data.components]
    if page_id is not None:
        payload["part"] = page_id
    return await call(
        ApiRequest(
            method="POST" if page_id is not None else "PATCH",
            route=route,
            body_json=json.dumps(payload),
        )
    )


def register_instances(server: MCPServer) -> None:
    """Expose every instance operation offered by both annotation endpoints."""

    @server.tool(annotations=READ)
    async def list_annotations(
        document_id: Identifier,
        page_id: Identifier,
        kind: AnnotationKind,
        transcription_id: Identifier | None = None,
        pagination: PageSelection | None = None,
    ) -> JsonValue:
        """List annotations by transcription or one fixed-size native page."""
        if transcription_id is not None and kind != "text":
            msg = "The transcription filter is only supported for text annotations."
            raise ToolError(msg)
        route = f"documents/{document_id}/parts/{page_id}/annotations/{kind}/"
        query = {"transcription": str(transcription_id)} if transcription_id else {}
        return await call(
            paginated_request(
                route,
                pagination,
                query=query,
                page_size_supported=False,
            )
            if pagination is not None
            else ApiRequest(
                method="GET",
                route=route,
                paginate=True,
                query=query,
            )
        )

    @server.tool(annotations=READ)
    async def get_annotation(
        target: AnnotationTarget, kind: AnnotationKind
    ) -> JsonValue:
        """Read an annotation, component values and its server-generated W3C form."""
        return await invoke("GET", target.route(kind))

    @server.tool(annotations=DELETE)
    async def delete_annotation(
        target: AnnotationTarget, kind: AnnotationKind
    ) -> JsonValue:
        """Delete an annotation and its component values from this page."""
        return await invoke("DELETE", target.route(kind))

    @server.tool(annotations=CREATE)
    async def create_image_annotation(
        document_id: Identifier,
        page_id: Identifier,
        data: ImageAnnotationCreate,
    ) -> JsonValue:
        """Create an image annotation on this page using a document taxonomy."""
        return await write_annotation(
            f"documents/{document_id}/parts/{page_id}/annotations/image/",
            data,
            page_id=page_id,
        )

    @server.tool(annotations=CHANGE)
    async def update_image_annotation(
        target: AnnotationTarget,
        changes: ImageAnnotationPatch,
    ) -> JsonValue:
        """Update image fields; components upsert by ID, [] preserves existing values.

        Set a component value to null to clear it. Its relation remains because
        the upstream API has no component-value deletion endpoint.
        """
        return await write_annotation(target.route("image"), changes)

    @server.tool(annotations=CREATE)
    async def create_text_annotation(
        document_id: Identifier,
        page_id: Identifier,
        data: TextAnnotationCreate,
    ) -> JsonValue:
        """Create a text span; use page line IDs and the document transcription ID."""
        return await write_annotation(
            f"documents/{document_id}/parts/{page_id}/annotations/text/",
            data,
            page_id=page_id,
        )

    @server.tool(annotations=CHANGE)
    async def update_text_annotation(
        target: AnnotationTarget,
        changes: TextAnnotationPatch,
    ) -> JsonValue:
        """Update text fields; components upsert by ID, [] preserves existing values.

        Set a component value to null to clear it. Its relation remains because
        the upstream API has no component-value deletion endpoint.
        """
        return await write_annotation(target.route("text"), changes)
