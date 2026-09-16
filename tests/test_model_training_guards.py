"""Active training allows naming changes but prevents conflicting mutations."""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from tests.model_fixture import ModelFixture, model_fixture, model_session
from tests.ontology_fixture import invoke

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize(
    "tool", ["job", "file_size", "replace_model_file", "delete_model"]
)
def test_training_model_rejects_conflicting_mutations(
    tmp_path: Path, tool: str
) -> None:
    source = tmp_path / "model.safetensors"
    _ = source.write_bytes(b"replacement")

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            args: dict[str, JsonValue] = {"model_id": 7}
            name = tool
            if tool in {"job", "file_size"}:
                name = "update_model"
                args["changes"] = {tool: 2}
            if tool == "replace_model_file":
                args["file_path"] = str(source)
            result = await session.call_tool(name, args)
            assert result.is_error

    with model_fixture() as fixture:
        fixture.model["training"] = True
        anyio.run(run, fixture)
    assert [request.method for request in fixture.requests] == ["GET"]


def test_training_model_can_be_renamed() -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            _ = await invoke(
                session, "update_model", {"model_id": 7, "changes": {"name": "Renamed"}}
            )

    with model_fixture() as fixture:
        fixture.model["training"] = True
        anyio.run(run, fixture)
    assert [request.method for request in fixture.requests] == ["GET", "PATCH"]
