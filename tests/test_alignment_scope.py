"""Alignment preflight refuses mismatched scopes and active-source overwrites."""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from tests.alignment_fixture import (
    ALIGN,
    FORCED,
    LAYER,
    MODEL,
    WITNESS,
    AlignmentFixture,
    alignment_fixture,
    alignment_job,
    alignment_session,
)

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.mark.parametrize(
    "issue",
    [
        "document_id",
        "source_id",
        "source_archived",
        "witness_id",
        "foreign_page",
        "foreign_type",
        "source_collision",
        "trimmed_collision",
        "source404",
        "witness403",
    ],
)
def test_ordinary_alignment_scope_failure_prevents_post(issue: str) -> None:
    # Given an invalid source, witness, selection or normalized source-name target.
    job = alignment_job()
    if issue == "foreign_page":
        job["parts"] = [999]
    if issue == "foreign_type":
        job["region_types"] = [999]
    if issue == "source_collision":
        job["layer_name"] = "Source"
    if issue == "trimmed_collision":
        job["layer_name"] = "  Source  "

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When ordinary alignment validates the acknowledged job.
            result = await session.call_tool(
                "align_document", {"document_id": 4, "job": job}
            )
            # Then acknowledgment cannot bypass source/scope protection.
            assert result.is_error

    with alignment_fixture() as fixture:
        if issue == "document_id":
            fixture.document["pk"] = 999
        if issue == "source_id":
            fixture.layer["pk"] = 999
        if issue == "source_archived":
            fixture.layer["archived"] = True
        if issue == "witness_id":
            fixture.responses["GET " + WITNESS] = {"pk": 999}
        if issue == "source404":
            fixture.failures["GET " + LAYER] = 404
        if issue == "witness403":
            fixture.failures["GET " + WITNESS] = 403
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)


@pytest.mark.parametrize(
    "issue", ["model_id", "model_kind", "model403", "foreign_page", "document_id"]
)
def test_forced_alignment_scope_preflight_blocks_bad_model_or_pages(issue: str) -> None:
    # Given an unreadable/wrong model or foreign requested page.
    job: dict[str, JsonValue] = {"model": 8, "transcription": 2}
    if issue == "foreign_page":
        job["parts"] = [999]

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When forced alignment checks only the scopes it can faithfully verify.
            result = await session.call_tool(
                "force_align_pages", {"document_id": 4, "job": job}
            )
            # Then no graph-replacement job is submitted.
            assert result.is_error

    with alignment_fixture() as fixture:
        if issue == "model_id":
            fixture.model["pk"] = 999
        if issue == "model_kind":
            fixture.model["job"] = "Segment"
        if issue == "model403":
            fixture.failures["GET " + MODEL] = 403
        if issue == "document_id":
            fixture.document["pk"] = 999
        anyio.run(run, fixture)
    assert all(method == "GET" for method, _, _ in fixture.requests)
    assert all(route != LAYER for _, route, _ in fixture.requests)


@pytest.mark.parametrize("tool", ["align_document", "force_align_pages"])
@pytest.mark.parametrize("status", [400, 500])
def test_native_action_failure_is_one_uncertain_submission(
    tool: str, status: int
) -> None:
    # Given a server failure, including forced native same-document layer rejection.
    job = (
        alignment_job()
        if tool == "align_document"
        else {"model": 8, "transcription": 999 if status == 400 else 2}
    )
    route = ALIGN if tool == "align_document" else FORCED

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When the native action rejects or fails after preflight.
            result = await session.call_tool(tool, {"document_id": 4, "job": job})
            # Then uncertainty is retained without automatic resubmission.
            assert result.is_error
            assert str(status) in result.model_dump_json()
            assert "may" in result.model_dump_json().lower()

    with alignment_fixture() as fixture:
        if tool == "align_document" or status == 500:
            fixture.failures["POST " + route] = status
        anyio.run(run, fixture)
    assert sum(method == "POST" for method, _, _ in fixture.requests) == 1
    assert fixture.requests[-1][0] == "POST"
    if tool == "force_align_pages":
        assert fixture.queued_pages == ([10] if status == 500 else [])


@pytest.mark.parametrize(
    ("filename", "content"),
    [("wrong.xml", b"text"), ("empty.txt", b""), ("binary.txt", b"\xff")],
)
def test_invalid_direct_witness_file_never_submits(
    tmp_path: Path, filename: str, content: bytes
) -> None:
    # Given a direct alignment reference with wrong format, empty or non-UTF-8 bytes.
    path = tmp_path / filename
    _ = path.write_bytes(content)

    async def run(fixture: AlignmentFixture) -> None:
        async with alignment_session(fixture) as session:
            # When the direct file path is validated for alignment.
            result = await session.call_tool(
                "align_document",
                {
                    "document_id": 4,
                    "job": alignment_job(
                        {"witness": {"kind": "file", "file_path": str(path)}}
                    ),
                },
            )
            # Then no alignment or standalone witness POST can occur.
            assert result.is_error

    with alignment_fixture() as fixture:
        anyio.run(run, fixture)
    assert not fixture.uploads
    assert all(method == "GET" for method, _, _ in fixture.requests)
