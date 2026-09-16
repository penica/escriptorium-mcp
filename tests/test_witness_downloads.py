"""Owned witness downloads share exclusive streaming storage and URL restrictions."""

import hashlib
from pathlib import Path

import anyio
import pytest

from tests.transcription_fixture import invoke
from tests.witness_fixture import (
    FILE,
    WITNESS,
    WitnessFixture,
    witness_fixture,
    witness_session,
)


def test_owned_witness_download_preserves_exact_bytes_and_checksum(
    tmp_path: Path,
) -> None:
    # Given a readable witness whose file URL belongs to configured storage.
    destination = tmp_path / "reference with spaces.txt"

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the reference file is downloaded to a new explicit local path.
            result = await invoke(
                session,
                "download_textual_witness",
                {
                    "witness_id": 7,
                    "destination": str(destination),
                },
            )
            # Then completion evidence describes the actual saved bytes.
            assert isinstance(result, dict)
            assert result["bytes"] == len(fixture.binary)
            assert result["sha256"] == hashlib.sha256(fixture.binary).hexdigest()
            assert result["status"] == "complete"
            assert Path(str(result["path"])) == destination

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert destination.read_bytes() == fixture.binary
    assert fixture.requests == [("GET", WITNESS, None), ("GET", FILE, None)]
    assert not destination.with_name(destination.name + ".part").exists()


@pytest.mark.parametrize(
    "location",
    [
        None,
        "/media/reference.txt",
        "/media/witnesses/",
        "/media/witnesses/../private",
        "/media/witnesses/%2e%2e/private",
        "/media/witnesses/%252e%252e/private",
        "/media/witnesses/witnesses/reference.txt",
        "/media/witnesses/reference.txt?token=x",
        "/media/witnesses/reference.txt#fragment",
        "/media/witnesses\\private.txt",
    ],
)
def test_untrusted_witness_file_path_never_requests_bytes(
    tmp_path: Path, location: str | None
) -> None:
    # Given absent, ambiguous or traversal-bearing native file metadata.
    destination = tmp_path / "reference.txt"

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When download resolves the witness storage URL.
            result = await session.call_tool(
                "download_textual_witness",
                {
                    "witness_id": 7,
                    "destination": str(destination),
                },
            )
            # Then malformed metadata is rejected before file access.
            assert result.is_error

    with witness_fixture() as fixture:
        fixture.witness["file"] = location
        anyio.run(run, fixture)
    assert fixture.requests == [("GET", WITNESS, None)]
    assert not destination.exists()


def test_foreign_file_url_does_not_send_credentials_or_network_request(
    tmp_path: Path,
) -> None:
    # Given a server-reported file URL pointing at an independent foreign listener.
    destination = tmp_path / "reference.txt"

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the owned witness metadata tries to redirect storage authority.
            result = await session.call_tool(
                "download_textual_witness",
                {
                    "witness_id": 7,
                    "destination": str(destination),
                },
            )
            # Then authentication never reaches the foreign origin.
            assert result.is_error

    with witness_fixture() as fixture, witness_fixture() as foreign:
        fixture.witness["file"] = foreign.url + "media/witnesses/reference.txt"
        anyio.run(run, fixture)
    assert not foreign.received
    assert not destination.exists()


@pytest.mark.parametrize("mode", ["redirect", "short", "missing"])
def test_unavailable_or_incomplete_file_is_not_published(
    tmp_path: Path, mode: str
) -> None:
    # Given a redirect, truncated body or missing stored file.
    destination = tmp_path / "reference.txt"

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When the existing streaming downloader encounters the failure.
            result = await session.call_tool(
                "download_textual_witness",
                {
                    "witness_id": 7,
                    "destination": str(destination),
                },
            )
            # Then it never publishes a completed local reference.
            assert result.is_error

    with witness_fixture() as fixture:
        if mode == "redirect":
            fixture.redirects[FILE] = "/other-storage.txt"
        if mode == "short":
            fixture.binary_faults["extra_length"] = 10
        if mode == "missing":
            fixture.binary_faults["status"] = 404
        anyio.run(run, fixture)
    assert not destination.exists()
    assert len(fixture.requests) == 2
    if mode == "short":
        assert destination.with_name(destination.name + ".part").exists()


@pytest.mark.parametrize("occupied_partial", [False, True])
def test_witness_download_never_overwrites_existing_path(
    tmp_path: Path, *, occupied_partial: bool
) -> None:
    # Given an existing destination or preserved partial download.
    destination = tmp_path / "reference.txt"
    occupied = (
        destination.with_name(destination.name + ".part")
        if occupied_partial
        else destination
    )
    _ = occupied.write_bytes(b"retain")

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When attempting a second publication at the occupied path.
            result = await session.call_tool(
                "download_textual_witness",
                {
                    "witness_id": 7,
                    "destination": str(destination),
                },
            )
            # Then refusal preserves the existing bytes without fetching the file.
            assert result.is_error

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert occupied.read_bytes() == b"retain"
    assert fixture.requests == [("GET", WITNESS, None)]


def test_witness_download_is_excluded_from_books_archive(tmp_path: Path) -> None:
    # Given the configured full-register archive rather than a scratch destination.
    books = tmp_path / "Books"
    books.mkdir()
    destination = books / "reference.txt"

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture, books) as session:
            # When requesting a witness file inside the register archive.
            result = await session.call_tool(
                "download_textual_witness",
                {
                    "witness_id": 7,
                    "destination": str(destination),
                },
            )
            # Then the shared storage policy refuses the unrelated artifact.
            assert result.is_error

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert not destination.exists()
    assert fixture.requests == [("GET", WITNESS, None)]


def test_encoded_controls_and_credential_urls_cannot_be_normalized_into_trust(
    tmp_path: Path,
) -> None:
    # Given malicious native URLs that generic URL parsers can silently normalize.
    destination = tmp_path / "reference.txt"

    async def run(fixture: WitnessFixture) -> None:
        locations = [
            "\x01" + fixture.url + "media/witnesses/reference.txt",
            "/media/witnesses/ref%00.txt",
            "/media/witnesses/ref%0a.txt",
            "/media/witnesses/sub%2fref.txt",
            "/media/witnesses/sub%255cref.txt",
            fixture.url.replace("http://", "http://user:secret@")
            + "media/witnesses/reference.txt",
            "http://127.0.0.1:0/media/witnesses/reference.txt",
        ]
        async with witness_session(fixture) as session:
            # When each URL is resolved after the owned metadata read.
            for location in locations:
                fixture.witness["file"] = location
                result = await session.call_tool(
                    "download_textual_witness",
                    {
                        "witness_id": 7,
                        "destination": str(destination),
                    },
                )
                # Then none can change origin or smuggle a storage path delimiter.
                assert result.is_error
        assert fixture.received == [("GET", WITNESS)] * len(locations)

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert not destination.exists()
