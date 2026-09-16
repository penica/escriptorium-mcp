"""Generated files cannot overwrite paths or enter the complete-books archive."""

from pathlib import Path

import anyio
import pytest

from tests.download_fixture import FILE, download_fixture
from tests.test_download_files import failed_file


@pytest.mark.parametrize("partial", [False, True])
def test_existing_destination_is_preserved(tmp_path: Path, *, partial: bool) -> None:
    destination = tmp_path / "export.zip"
    occupied = (
        destination.with_name(destination.name + ".part") if partial else destination
    )
    _ = occupied.write_bytes(b"retain original")
    with download_fixture() as fixture:
        anyio.run(failed_file, fixture, destination)
    assert occupied.read_bytes() == b"retain original"
    assert ("GET", FILE) not in fixture.requests


@pytest.mark.parametrize("name", ["CON.zip", "bad?.zip", "trailing.", "bad:name.zip"])
def test_nonportable_filename_is_rejected(tmp_path: Path, name: str) -> None:
    with download_fixture() as fixture:
        anyio.run(failed_file, fixture, tmp_path / name)
    assert ("GET", FILE) not in fixture.requests
    assert not list(tmp_path.iterdir())


def test_books_archive_rejects_individual_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "Books"
    root.mkdir()
    monkeypatch.setenv("ESCRIPTORIUM_BOOKS_ROOT", str(root))
    with download_fixture() as fixture:
        anyio.run(failed_file, fixture, root / "export.zip")
    assert ("GET", FILE) not in fixture.requests
    assert not list(root.iterdir())
