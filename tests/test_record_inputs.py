"""Native record field limits and query grammar are enforced before requests."""

from collections.abc import Mapping

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from escriptorium_mcp.project_models import ProjectCreateSettings, ProjectPatch
from escriptorium_mcp.record_models import DocumentCreate, DocumentPatch
from escriptorium_mcp.record_query_models import (
    DocumentFilters,
    ElementQuery,
    ProjectFilters,
    StatisticsOptions,
)


@pytest.mark.parametrize("expression", ["1", "none", "1,2", "1|2", "none|1"])
def test_native_tag_filter_grammar_accepts_supported_expressions(
    expression: str,
) -> None:
    # Given a supported native AND/OR or untagged expression.
    # When parsed, then exact spelling is retained for the server.
    assert ProjectFilters(tags=expression).tags == expression


@pytest.mark.parametrize(
    "expression", ["", "0", "-1", "1,", "|1", "1,,2", "1,2|3", "none,1"]
)
def test_invalid_tag_filter_grammar(expression: str) -> None:
    # Given empty terms, mixed operators or unsupported untagged AND.
    # When parsing a filter, then it is rejected before an API call.
    with pytest.raises(ValidationError):
        _ = ProjectFilters(tags=expression)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ProjectPatch, {}),
        (ProjectPatch, {"name": None}),
        (ProjectPatch, {"name": "N" * 513}),
        (ProjectPatch, {"name": "   "}),
        (ProjectCreateSettings, {"guidelines": "not a URL"}),
        (ProjectCreateSettings, {"guidelines": "https://example.org/" + "x" * 190}),
        (ProjectCreateSettings, {"tags": None}),
        (ProjectCreateSettings, {"tags": [31, 31]}),
        (DocumentPatch, {"tags": [11, 11]}),
        (DocumentPatch, {"tags": [True]}),
        (DocumentPatch, {"show_confidence_viz": None}),
        (DocumentPatch, {"main_script": None}),
        (DocumentPatch, {"project": None}),
        (DocumentPatch, {"name": "N" * 513}),
        (DocumentCreate, {"name": "N" * 513, "project": "old", "main_script": "Latin"}),
        (DocumentFilters, {"project": "old"}),
        (DocumentFilters, {"project": True}),
        (DocumentFilters, {"ordering": ["owner"]}),
        (ProjectFilters, {"ordering": []}),
        (ProjectFilters, {"owner": 1}),
        (StatisticsOptions, {"ordering": "name"}),
        (ElementQuery, {"category": "pages", "type_id": 1}),
        (ElementQuery, {"category": "regions", "type_id": 0}),
        (ElementQuery, {"category": "regions", "type_id": "3"}),
    ],
)
def test_invalid_record_inputs(
    model: type[BaseModel], payload: Mapping[str, JsonValue]
) -> None:
    # Given an unsupported field value, scope selector or native setting.
    # When parsing at the public boundary, then no valid input is constructed.
    with pytest.raises(ValidationError):
        _ = model.model_validate(payload)
