from pathlib import Path
from typing import ClassVar, Final

import anyio
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from escriptorium_mcp.server import create_server


class ToolContract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    input_schema: JsonValue = Field(alias="inputSchema")
    output_schema: JsonValue = Field(alias="outputSchema")
    annotations: dict[str, JsonValue]


BASELINE: Final = Path(__file__).resolve().parents[1] / "contracts/v1-tools.json"
CONTRACTS: Final = TypeAdapter(list[ToolContract])
SCHEMA_MAPS: Final = frozenset(
    {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"}
)
SCHEMA_VALUES: Final = frozenset(
    {
        "additionalProperties",
        "unevaluatedProperties",
        "items",
        "contains",
        "propertyNames",
        "not",
        "if",
        "then",
        "else",
        "additionalItems",
        "unevaluatedItems",
        "contentSchema",
        "allOf",
        "anyOf",
        "oneOf",
        "prefixItems",
    }
)
PROSE: Final = frozenset({"title", "description", "examples", "$comment"})


def machine_schema(value: JsonValue, *, named_map: bool = False) -> JsonValue:
    """Remove schema prose while retaining fields actually named title/description."""
    match value:
        case dict():
            return {
                key: (
                    machine_schema(item, named_map=key in SCHEMA_MAPS and not named_map)
                    if named_map or key in SCHEMA_MAPS | SCHEMA_VALUES
                    else item
                )
                for key, item in value.items()
                if named_map or key not in PROSE
            }
        case list():
            return [machine_schema(item) for item in value]
        case _:
            return value


def test_existing_tools_preserve_reviewed_v1_contract() -> None:
    # Given the independently checked-in 1.x compatibility baseline.
    expected = CONTRACTS.validate_json(BASELINE.read_bytes())
    # When a client discovers the actual server catalogue.
    tools = anyio.run(create_server().list_tools)
    actual = {
        tool.name: ToolContract.model_validate_json(tool.model_dump_json(by_alias=True))
        for tool in tools
    }
    # Then existing names, machine schemas, and safety hints remain unchanged.
    for contract in expected:
        assert contract.name in actual, f"Removed stable tool: {contract.name}"
        observed = actual[contract.name]
        assert machine_schema(observed.input_schema) == contract.input_schema, (
            f"Review input compatibility for {contract.name}; see docs/STABILITY.md"
        )
        assert machine_schema(observed.output_schema) == contract.output_schema, (
            f"Review output compatibility for {contract.name}; see docs/STABILITY.md"
        )
        assert {
            key: value for key, value in observed.annotations.items() if key != "title"
        } == contract.annotations, f"Review safety hints for {contract.name}"


def test_normalization_preserves_property_names_and_literal_defaults() -> None:
    # Given prose-like names that belong to data, not schema documentation.
    schema: JsonValue = {
        "title": "Presentation only",
        "properties": {"description": {"type": "string", "title": "Description"}},
        "default": {"title": "Meaningful default"},
    }
    # When normalizing the compatibility contract.
    normalized = machine_schema(schema)
    # Then only schema prose is discarded.
    assert normalized == {
        "properties": {"description": {"type": "string"}},
        "default": {"title": "Meaningful default"},
    }
