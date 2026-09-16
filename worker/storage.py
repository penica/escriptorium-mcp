"""Portable archive configuration, filenames and exclusive file publication."""

import os
import re
import shutil
from pathlib import Path, PureWindowsPath
from typing import Final

CONTROL_LIMIT: Final = 32
FILENAME_BYTES: Final = 160


def books_root() -> Path | None:
    """Read an explicit absolute archive location in this host's path syntax."""
    configured = os.environ.get("ESCRIPTORIUM_BOOKS_ROOT", "")
    if not configured:
        return None
    root = Path(configured).expanduser()
    if not root.is_absolute():
        message = "ESCRIPTORIUM_BOOKS_ROOT must be an absolute host path"
        raise ValueError(message)
    return root.resolve()


def portable_component(value: str) -> str:
    """Reject names which change meaning or fail on Windows shares."""
    if (
        value.endswith((" ", "."))
        or PureWindowsPath(value).is_reserved()
        or any(character in value for character in '<>:"/\\|?*')
        or any(ord(character) < CONTROL_LIMIT for character in value)
    ):
        message = "Filename is not portable across macOS, Windows and Linux"
        raise ValueError(message)
    return value


def scan_filename(original: str) -> str:
    """Produce a bounded share-safe suffix; callers prefix the unique page key."""
    safe = re.sub(r"[^\w.-]", "_", original).rstrip(" .") or "scan"
    while len(safe.encode("utf-8")) > FILENAME_BYTES:
        safe = safe[1:]
    return safe


def finish_file(temporary: Path, destination: Path) -> None:
    """Publish without hardlinks or clobbering; keep the partial on failure."""
    with temporary.open("rb") as source:
        output = destination.open("xb")
        try:
            with output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
        except OSError:
            destination.unlink()
            raise
    temporary.unlink()
