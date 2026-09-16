"""Model downloads validate URL trust, revisions and exclusive file publication."""

import hashlib
from pathlib import Path
from urllib.parse import unquote

import anyio
import pytest

from tests.model_fixture import ModelFixture, model_fixture, model_session
from tests.ontology_fixture import invoke


@pytest.mark.parametrize("revision", [None, "revision-1"])
def test_model_download_streams_selected_artifact(
    tmp_path: Path, revision: str | None
) -> None:
    destination = tmp_path / "download.safetensors"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await invoke(
                session,
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                    "revision": revision,
                },
            )
            assert isinstance(result, dict)
            assert result["bytes"] == len(fixture.binary)
            assert result["sha256"] == hashlib.sha256(fixture.binary).hexdigest()
            assert result["status"] == "complete"
            assert Path(str(result["path"])) == destination

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert destination.read_bytes() == fixture.binary
    assert not destination.with_name(destination.name + ".part").exists()
    expected = (
        "/media/models/hash/epoch=01.ckpt"
        if revision
        else "/media/models/hash/current.safetensors"
    )
    assert unquote(fixture.requests[-1].path) == expected


@pytest.mark.parametrize("status", [404, 302])
def test_missing_or_redirected_model_file_never_publishes(
    tmp_path: Path, status: int
) -> None:
    destination = tmp_path / "download.safetensors"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                },
            )
            assert result.is_error

    with model_fixture(binary_status=status) as fixture:
        anyio.run(run, fixture)
    assert not destination.exists()
    assert len(fixture.requests) == 2


def test_incomplete_model_file_never_publishes(tmp_path: Path) -> None:
    destination = tmp_path / "download.safetensors"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                },
            )
            assert result.is_error

    with model_fixture(length_extra=4) as fixture:
        anyio.run(run, fixture)
    assert not destination.exists()


@pytest.mark.parametrize("partial", [False, True])
def test_existing_download_destination_is_preserved(
    tmp_path: Path, *, partial: bool
) -> None:
    destination = tmp_path / "download.safetensors"
    occupied = (
        destination.with_name(destination.name + ".part") if partial else destination
    )
    _ = occupied.write_bytes(b"retain original")

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                },
            )
            assert result.is_error

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert occupied.read_bytes() == b"retain original"
    assert all(request.path.startswith("/api/") for request in fixture.requests)


@pytest.mark.parametrize(
    "location",
    [None, "http://other.invalid/model", "http://user:secret@127.0.0.1/model"],
)
def test_untrusted_current_file_never_downloads(
    tmp_path: Path, location: str | None
) -> None:
    destination = tmp_path / "download.safetensors"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                },
            )
            assert result.is_error
            assert "fixture-key" not in str(result.content)

    with model_fixture() as fixture:
        fixture.model["file"] = location
        anyio.run(run, fixture)
    assert not destination.exists()
    assert len(fixture.requests) == 1


@pytest.mark.parametrize(
    "path",
    [
        "../private",
        "models/hash/../../private",
        "models/hash/%2e%2e/private",
        "http://other.invalid/file",
    ],
)
def test_checkpoint_path_traversal_is_rejected(tmp_path: Path, path: str) -> None:
    destination = tmp_path / "checkpoint.ckpt"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                    "revision": "revision-1",
                },
            )
            assert result.is_error

    with model_fixture() as fixture:
        fixture.model["versions"] = [{"revision": "revision-1", "data": {"file": path}}]
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert not destination.exists()


@pytest.mark.parametrize("scenario", ["missing", "duplicate", "ambiguous_prefix"])
def test_checkpoint_selection_must_be_unambiguous(
    tmp_path: Path, scenario: str
) -> None:
    destination = tmp_path / "checkpoint.ckpt"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                    "revision": "revision-1",
                },
            )
            assert result.is_error

    with model_fixture() as fixture:
        if scenario == "missing":
            fixture.model["versions"] = []
        if scenario == "duplicate":
            versions = fixture.model["versions"]
            assert isinstance(versions, list)
            fixture.model["versions"] = versions + versions
        if scenario == "ambiguous_prefix":
            fixture.model["file"] = (
                fixture.url + "media/models/other/models/current.safetensors"
            )
        anyio.run(run, fixture)
    assert len(fixture.requests) == 1
    assert not destination.exists()


def test_model_download_cannot_write_to_books_archive(tmp_path: Path) -> None:
    books = tmp_path / "Books"
    books.mkdir()
    destination = books / "model.safetensors"

    async def run(fixture: ModelFixture) -> None:
        async with model_session(fixture, books) as session:
            result = await session.call_tool(
                "download_model",
                {
                    "model_id": 7,
                    "destination": str(destination),
                },
            )
            assert result.is_error

    with model_fixture() as fixture:
        anyio.run(run, fixture)
    assert not destination.exists()
    assert all(request.path.startswith("/api/") for request in fixture.requests)
