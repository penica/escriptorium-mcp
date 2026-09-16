"""Model management protocol contracts preserve permissions and exact payloads."""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from pydantic import JsonValue, TypeAdapter

from tests.model_fixture import ModelFixture, model_fixture, model_session
from tests.ontology_fixture import invoke


@pytest.mark.parametrize(("job", "label"), [(1, b"Segment"), (2, b"Recognize")])
def test_model_upload_translates_display_choice(
    tmp_path: Path,
    job: int,
    label: bytes,
) -> None:
    source = tmp_path / "new.safetensors"
    _ = source.write_bytes(b"fixture weights")

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            _ = await invoke(
                session,
                "upload_model",
                {
                    "model": {
                        "file_path": str(source),
                        "name": "New model",
                        "job": job,
                    }
                },
            )

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    request = fixture.requests[0]
    assert request.method == "POST"
    assert b'name="job"\r\n\r\n' + label + b"\r\n" in request.body
    assert b"fixture weights" in request.body


@pytest.mark.parametrize("arguments", [{}, {"document_id": 4, "job": 1}])
def test_model_listing_filters(arguments: dict[str, JsonValue]) -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await invoke(session, "list_models", arguments)
            assert result == {"count": 1, "next": None, "results": [fixture.model]}

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert parse_qs(urlsplit(fixture.requests[0].path).query) == (
        {"documents": ["4"], "job": ["1"]} if arguments else {}
    )


@pytest.mark.parametrize("changes", [{"name": "Renamed"}, {"job": 2, "file_size": 0}])
def test_model_update_only_sends_selected_fields(changes: dict[str, JsonValue]) -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            _ = await invoke(
                session, "update_model", {"model_id": 7, "changes": changes}
            )

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert [request.method for request in fixture.requests] == ["GET", "PATCH"]
    body = TypeAdapter[JsonValue](JsonValue).validate_json(fixture.requests[-1].body)
    assert body == (
        {"job": "Recognize", "file_size": 0} if "job" in changes else changes
    )


@pytest.mark.parametrize(
    "changes",
    [{}, {"name": None}, {"job": None}, {"file_size": -1}, {"documents": [4]}],
)
def test_invalid_model_changes_never_reach_backend(
    changes: dict[str, JsonValue],
) -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "update_model", {"model_id": 7, "changes": changes}
            )
            assert result.is_error

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.requests


@pytest.mark.parametrize("tool", ["update_model", "replace_model_file", "delete_model"])
def test_shared_model_mutations_are_rejected(tool: str, tmp_path: Path) -> None:
    source = tmp_path / "model.safetensors"
    _ = source.write_bytes(b"fixture weights")

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            args: dict[str, JsonValue] = {"model_id": 7}
            if tool == "update_model":
                args["changes"] = {"name": "Renamed"}
            if tool == "replace_model_file":
                args["file_path"] = str(source)
            result = await session.call_tool(tool, args)
            assert result.is_error

    with model_fixture() as fixture:
        fixture.model["rights"] = "user"
        anyio.run(run, fixture)
    assert [request.method for request in fixture.requests] == ["GET"]


def test_model_file_replacement_uses_patch_and_computed_size(tmp_path: Path) -> None:
    source = tmp_path / "model.safetensors"
    _ = source.write_bytes(b"replacement bytes")

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            _ = await invoke(
                session, "replace_model_file", {"model_id": 7, "file_path": str(source)}
            )

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert [request.method for request in fixture.requests] == ["GET", "PATCH"]
    request = fixture.requests[-1]
    assert request.content_type.startswith("multipart/form-data;")
    assert b'name="file_size"\r\n\r\n17\r\n' in request.body
    assert b"replacement bytes" in request.body


def test_model_deletion_uses_delete() -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await invoke(session, "delete_model", {"model_id": 7})
            assert result == {"status": "success", "http_status": 204}

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert [request.method for request in fixture.requests] == ["GET", "DELETE"]


@pytest.mark.parametrize("tool", ["list_model_versions", "get_model_documents"])
def test_model_metadata_inspection_preserves_contract(tool: str) -> None:
    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await invoke(session, tool, {"model_id": 7})
            assert isinstance(result, dict)
            assert result["model_id"] == 7
            if tool == "list_model_versions":
                assert result["versions"] == fixture.model["versions"]
                assert result["current_file"] == fixture.model["file"]
            else:
                assert result["document_ids"] == [4, 8]
                assert result["associations_editable"] is False

    with model_fixture() as fixture:
        anyio.run(run, fixture)
