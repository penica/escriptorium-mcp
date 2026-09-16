"""Alignment JSON/multipart payloads retain required native defaults and zeros."""

from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue

from tests.alignment_fixture import (
    ALIGN,
    FORCED,
    GROUPS,
    LAYER,
    PARTS,
    AlignmentFixture,
    alignment_fixture,
    alignment_job,
    alignment_session,
)
from tests.transcription_fixture import invoke


def test_alignment_submission_defaults() -> None:
    # Given an acknowledged ordinary alignment job with omitted native options.
    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When the alignment is submitted.
            result = await invoke(
                session, "align_document", {"document_id": 4, "job": alignment_job()}
            )
            # Then acceptance retains the exact native response.
            assert result == {"status": "ok"}

    with alignment_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        ALIGN,
        {
            "transcription": 2,
            "existing_witness": 7,
            "layer_name": "Aligned",
            "n_gram": 25,
            "gap": 600,
            "threshold": 0.8,
            "region_types": ["3", "Undefined", "Orphan"],
            "beam_size": 20,
            "max_offset": 0,
            "merge": False,
            "add_hyphens": False,
            "full_doc": True,
        },
    )
    assert all(route not in {PARTS, GROUPS} for _, route, _ in fixture.requests)


@pytest.mark.parametrize("offset", [0, 80])
def test_offset_search_and_zero_threshold_reach_native_api(offset: int) -> None:
    # Given explicit selected pages, region sentinels and offset search.
    job = alignment_job(
        {
            "parts": [11],
            "region_types": [3, "Orphan"],
            "search": {"kind": "offset", "max_offset": offset},
            "threshold": 0,
            "n_gram": 2,
            "gap": 1,
            "merge": True,
            "add_hyphens": True,
            "full_doc": False,
        }
    )

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When the exact search mode is submitted.
            result = await invoke(
                session, "align_document", {"document_id": 4, "job": job}
            )
            # Then the accepted response remains raw.
            assert result == {"status": "ok"}

    with alignment_fixture() as fixture:
        anyio.run(run, fixture)
    assert fixture.requests[-1] == (
        "POST",
        ALIGN,
        {
            "transcription": 2,
            "existing_witness": 7,
            "layer_name": "Aligned",
            "n_gram": 2,
            "gap": 1,
            "threshold": 0,
            "region_types": ["3", "Orphan"],
            "parts": [11],
            "beam_size": 0,
            "max_offset": offset,
            "merge": True,
            "add_hyphens": True,
            "full_doc": False,
        },
    )
    assert ("GET", PARTS + "?page=2", None) in fixture.requests


def test_direct_witness_file_upload_preserves_bytes_without_standalone_create(
    tmp_path: Path,
) -> None:
    # Given UTF-8 reference text whose basename exceeds the standalone limit.
    path = tmp_path / ("w" * 110 + ".txt")
    content = b"\xef\xbb\xbfReference\r\ntext\n"
    _ = path.write_bytes(content)
    job = alignment_job(
        {
            "witness": {"kind": "file", "file_path": str(path)},
            "search": {"kind": "beam", "beam_size": 100},
        }
    )

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When the direct alignment upload path is used.
            result = await invoke(
                session, "align_document", {"document_id": 4, "job": job}
            )
            # Then native acceptance does not require standalone witness creation.
            assert result == {"status": "ok"}

    with alignment_fixture() as fixture:
        anyio.run(run, fixture)
    assert [r for r in fixture.requests if r[0] == "POST"] == [("POST", ALIGN, None)]
    assert len(fixture.uploads) == 1
    raw = fixture.uploads[0]
    assert b'name="witness_file"' in raw
    assert content in raw
    assert b'name="beam_size"\r\n\r\n100\r\n' in raw
    assert b'name="max_offset"\r\n\r\n0\r\n' in raw
    assert b'name="acknowledge_target_reuse"' not in raw
    assert b'name="existing_witness"' not in raw


@pytest.mark.parametrize("parts", [None, [11]])
def test_forced_alignment_delegates_archived_layer_validation_to_native_action(
    parts: list[int] | None,
) -> None:
    # Given an archived layer hidden by the active-only detail route.
    job: dict[str, JsonValue] = {"model": 8, "transcription": 2}
    if parts is not None:
        job["parts"] = list[JsonValue](parts)

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When forced alignment selects that layer by ID.
            result = await invoke(
                session, "force_align_pages", {"document_id": 4, "job": job}
            )
            # Then the authoritative native layer validation can accept it.
            assert result == {"status": "success"}

    with alignment_fixture() as fixture:
        fixture.failures["GET " + LAYER] = 404
        anyio.run(run, fixture)
    assert all(route not in {LAYER, GROUPS} for _, route, _ in fixture.requests)
    assert fixture.requests[-1] == ("POST", FORCED, job)


def test_acknowledged_target_name_is_passed_without_false_archived_absence_check() -> (
    None
):
    # Given a target potentially hidden by active-only transcription listings.
    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When explicit target reuse is acknowledged for that exact name.
            result = await invoke(
                session,
                "align_document",
                {
                    "document_id": 4,
                    "job": alignment_job({"layer_name": "  Hidden archived target  "}),
                },
            )
            # Then native acceptance preserves the chosen normalized target.
            assert result == {"status": "ok"}

    with alignment_fixture() as fixture:
        anyio.run(run, fixture)
    body = fixture.requests[-1][2]
    assert isinstance(body, dict)
    assert body["layer_name"] == "Hidden archived target"
    assert all(
        route != "/api/documents/4/transcriptions/" for _, route, _ in fixture.requests
    )


@pytest.mark.parametrize("missing", [True, False])
def test_forced_alignment_allows_absent_model_job_metadata(*, missing: bool) -> None:
    # Given a readable model whose native representation omits job classification.
    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When forced alignment delegates binary compatibility to the server.
            result = await invoke(
                session,
                "force_align_pages",
                {"document_id": 4, "job": {"model": 8, "transcription": 2}},
            )
            # Then absence of optional classification does not imply wrong model kind.
            assert result == {"status": "success"}

    with alignment_fixture() as fixture:
        if missing:
            _ = fixture.model.pop("job")
        else:
            fixture.model["job"] = None
        anyio.run(run, fixture)
