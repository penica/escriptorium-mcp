"""Read-only global font catalogue metadata; never download or install fonts."""

from mcp.server.mcpserver.tools import Tool
from pydantic import JsonValue

from escriptorium_mcp.api import READ, ApiRequest
from escriptorium_mcp.bridge import Identifier, call
from escriptorium_mcp.font_scope import read_font
from escriptorium_mcp.pagination import PageSelection, paginated_request
from escriptorium_mcp.strict_tools import strict_tool


def build_font_tools() -> list[Tool]:
    """Build strict catalogue reads without exposing unsupported font mutations."""

    async def list_fonts(pagination: PageSelection | None = None) -> JsonValue:
        """List authenticated instance-wide font metadata with strict pagination.

        Preserve native metrics and storage URLs without fetching font bytes.
        Omit pagination to follow every page, or select one fixed-size native page.
        An empty catalogue means no available fonts; missing API remains an error.
        Uploading fonts and editing metrics require the native admin interface.
        """
        return await call(
            paginated_request("fonts/", pagination, page_size_supported=False)
            if pagination is not None
            else ApiRequest(
                method="GET", route="fonts/", paginate=True, strict_pagination=True
            )
        )

    async def get_font(font_id: Identifier) -> JsonValue:
        """Read one font's native metadata, retaining zero/null and negative metrics.

        A URL is metadata, not proof of file availability or successful rendering.
        This operation never downloads, executes or installs the font file.
        """
        return await read_font(font_id)

    return [strict_tool(list_fonts, READ), strict_tool(get_font, READ)]
