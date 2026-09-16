import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp import ontology_tools
from escriptorium_mcp.api import ApiRequest
from escriptorium_mcp.ontology_models import TypeDefinition


@pytest.mark.parametrize("color", [None, "", "#abcdef"])
def test_explicit_color_is_rejected_before_write_when_unsupported(
    monkeypatch: pytest.MonkeyPatch, color: str | None
) -> None:
    async def unsupported(_kind: str) -> bool:
        return False

    monkeypatch.setattr(ontology_tools, "supports_type_color", unsupported)
    with pytest.raises(ToolError):
        anyio.run(
            ontology_tools.check_color, "line", TypeDefinition(name="x", color=color)
        )


def test_omitted_color_needs_no_capability_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected(_request: ApiRequest) -> JsonValue:
        pytest.fail("Omitted color must not require OPTIONS")

    monkeypatch.setattr(ontology_tools, "call", unexpected)
    anyio.run(ontology_tools.check_color, "line", TypeDefinition(name="x"))
