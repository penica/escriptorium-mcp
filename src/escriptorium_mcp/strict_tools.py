"""Build native MCP tools that reject unsupported top-level arguments."""

from collections.abc import Awaitable, Callable
from typing import ParamSpec

from mcp.server.mcpserver.tools import Tool
from mcp_types import ToolAnnotations
from pydantic import JsonValue

Parameters = ParamSpec("Parameters")


def strict_tool(
    function: Callable[Parameters, Awaitable[JsonValue]], annotations: ToolAnnotations
) -> Tool:
    """Keep runtime argument rejection and the advertised schema consistent."""
    tool = Tool.from_function(function, annotations=annotations)
    model = tool.fn_metadata.arg_model
    model.model_config["extra"] = "forbid"
    model.model_config["hide_input_in_errors"] = True
    _ = model.model_rebuild(force=True)
    tool.parameters = model.model_json_schema(by_alias=True)
    return tool
