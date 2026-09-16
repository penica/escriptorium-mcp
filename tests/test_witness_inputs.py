"""Witness file and explicit ownership acknowledgment boundaries."""

from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.witness_models import WitnessPatch, WitnessUpload
from tests.witness_fixture import WitnessFixture, witness_fixture, witness_session


@pytest.mark.parametrize("ack", [False, None, 0, 1, "true", "false", "1"])
def test_upload_requires_exact_true_acknowledgment(
    tmp_path: Path, ack: JsonValue
) -> None:
    # Given JSON values that compare/coerce to booleans but are not exact true.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Text", encoding="utf-8")
    # When constructing the upload contract, then implicit acknowledgment is refused.
    with pytest.raises(ValidationError):
        _ = WitnessUpload.model_validate(
            {
                "name": "Reference",
                "file_path": uploaded,
                "acknowledge_unverified_ownership": ack,
            }
        )


def test_name_fields_and_required_acknowledgment(tmp_path: Path) -> None:
    # Given existing local text and native name boundaries.
    uploaded = tmp_path / "reference.txt"
    _ = uploaded.write_text("Text", encoding="utf-8")
    for patch in (
        {},
        {"name": None},
        {"file_path": None},
        {"name": " "},
        {"name": "N" * 257},
        {"owner": "other"},
    ):
        # When invalid mutation metadata is parsed, then no usable patch is produced.
        with pytest.raises(ValidationError):
            _ = WitnessPatch.model_validate(patch)
    with pytest.raises(ValidationError):
        _ = WitnessUpload.model_validate({"name": "Reference", "file_path": uploaded})
    assert WitnessPatch.model_validate({"name": " N "}).name == "N"
    assert WitnessPatch.model_validate({"name": "N" * 256}).name == "N" * 256


def test_invalid_local_files_never_reach_api(tmp_path: Path) -> None:
    # Given an empty file, invalid UTF-8, unsupported extension and oversized basename.
    files = [
        tmp_path / "empty.txt",
        tmp_path / "binary.txt",
        tmp_path / "wrong.xml",
        tmp_path / ("n" * 97 + ".txt"),
    ]
    for path, data in zip(files, [b"", b"\xff\xfe", b"Text", b"Text"], strict=True):
        _ = path.write_bytes(data)

    async def run(fixture: WitnessFixture) -> None:
        async with witness_session(fixture) as session:
            # When invalid files are offered for upload or owned replacement.
            for path in files:
                uploaded = await session.call_tool(
                    "upload_textual_witness",
                    {
                        "upload": {
                            "name": "Reference",
                            "file_path": str(path),
                            "acknowledge_unverified_ownership": True,
                        }
                    },
                )
                replaced = await session.call_tool(
                    "update_textual_witness",
                    {
                        "witness_id": 7,
                        "changes": {"file_path": str(path)},
                    },
                )
                # Then no multipart mutation is attempted for unsafe local inputs.
                assert uploaded.is_error
                assert replaced.is_error

    with witness_fixture() as fixture:
        anyio.run(run, fixture)
    assert not [r for r in fixture.requests if r[0] != "GET"]
    assert not fixture.uploads
