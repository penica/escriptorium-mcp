"""Source variants reject contradictory inputs before reaching the API."""

from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from escriptorium_mcp.import_models import ImportSource


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"kind": "zip", "file_path": "book.zip"},
        {"kind": "iiif_url"},
        {"kind": "iiif_url", "url": "ftp://example.org/book"},
        {"kind": "iiif_url", "url": "not a URL"},
        {"kind": "iiif_url", "url": "https://example.org", "file_path": "book.xml"},
        {"kind": "iiif_url", "url": "https://example.org", "transcription_id": 2},
        {"kind": "pdf_file", "file_path": "book.pdf", "name": "OCR"},
        {"kind": "xml_file", "file_path": "book.xml", "name": ""},
        {"kind": "xml_file", "file_path": "book.xml", "name": "   "},
        {"kind": "xml_file", "file_path": "book.xml", "name": "x" * 257},
        {"kind": "xml_file", "file_path": "book.xml", "name": None},
        {"kind": "xml_file", "file_path": "book.xml", "transcription_id": None},
        {"kind": "xml_file", "file_path": "book.xml", "transcription_id": 0},
        {
            "kind": "xml_file",
            "file_path": "book.xml",
            "name": "OCR",
            "transcription_id": 2,
        },
        {
            "kind": "mets_url",
            "url": "https://example.org/book.xml",
            "name": "prefix",
            "prefix_transcription_id": 2,
        },
        {
            "kind": "mets_url",
            "url": "https://example.org/book.xml",
            "prefix_transcription_id": None,
        },
        {"kind": "mets_file", "file_path": "book.xml", "transcription_id": 2},
        {"kind": "mets_url", "url": "https://example.org/book.xml", "override": None},
    ],
)
def test_invalid_source_is_rejected(
    source: dict[str, JsonValue], tmp_path: Path
) -> None:
    # Given a contradictory or malformed source variant.
    source = dict(source)
    filename = source.get("file_path")
    if isinstance(filename, str):
        path = tmp_path / filename
        _ = path.write_bytes(b"fixture")
        source["file_path"] = str(path)
    adapter = TypeAdapter[ImportSource](ImportSource)
    # When the input crosses the typed boundary, then it is rejected.
    with pytest.raises(ValidationError):
        _ = adapter.validate_python(source)


def test_name_boundary_is_preserved(tmp_path: Path) -> None:
    # Given the largest supported import name and a real local XML file.
    path = tmp_path / "book.xml"
    _ = path.write_text("<Page/>")
    adapter = TypeAdapter[ImportSource](ImportSource)
    # When the source is parsed.
    source = adapter.validate_python(
        {"kind": "xml_file", "file_path": str(path), "name": "x" * 256}
    )
    # Then the full name survives serialization without truncation.
    assert source.model_dump()["name"] == "x" * 256


@pytest.mark.parametrize(
    ("kind", "suffix"),
    [
        ("pdf_file", ".PDF"),
        ("xml_file", ".XML"),
        ("xml_file", ".ZIP"),
        ("mets_file", ".XML"),
        ("mets_file", ".ZIP"),
    ],
)
def test_uppercase_suffix_is_rejected_before_native_case_sensitive_dispatch(
    tmp_path: Path, kind: str, suffix: str
) -> None:
    # Given a real file with a suffix the native parser does not recognize.
    path = tmp_path / ("book" + suffix)
    _ = path.write_bytes(b"fixture")
    adapter = TypeAdapter[ImportSource](ImportSource)
    # When parsed as an explicit source, then the misleading extension is rejected.
    with pytest.raises(ValidationError):
        _ = adapter.validate_python({"kind": kind, "file_path": str(path)})
