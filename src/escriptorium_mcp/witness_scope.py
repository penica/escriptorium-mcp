"""Owned witness identity and bounded-memory local text-file preflight."""

import codecs
from functools import partial
from pathlib import Path
from typing import Final

import anyio
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from escriptorium_mcp.api import invoke
from escriptorium_mcp.bridge import Identifier
from escriptorium_mcp.witness_models import WitnessIdentity

CHUNK_SIZE: Final = 64 * 1024
STANDALONE_FILENAME_LIMIT: Final = 100
ALIGNMENT_STEM_LIMIT: Final = 256


async def read_witness(witness_id: Identifier) -> JsonValue:
    """Verify owned detail identity while retaining all raw native metadata."""
    value = await invoke("GET", f"textual-witnesses/{witness_id}/")
    if WitnessIdentity.model_validate(value).pk != witness_id:
        msg = "The server returned a different textual witness; no writes were sent."
        raise ToolError(msg)
    return value


def _validate_file(path: Path, *, standalone: bool) -> None:
    """Validate streamed UTF-8 without rewriting BOMs, newlines or text bytes."""
    if path.suffix.lower() != ".txt":
        msg = "Textual witness files must have a .txt extension."
        raise ToolError(msg)
    limit = STANDALONE_FILENAME_LIMIT if standalone else ALIGNMENT_STEM_LIMIT
    label = path.name if standalone else path.stem
    if len(label) > limit:
        msg = f"Witness filename exceeds its native limit of {limit} characters."
        raise ToolError(msg)
    try:
        decoder = codecs.getincrementaldecoder("utf-8")()
        size = 0
        with path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                size += len(chunk)
                _ = decoder.decode(chunk)
        _ = decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        msg = "Textual witness files must contain valid UTF-8 text."
        raise ToolError(msg) from None
    except OSError:
        msg = "The textual witness file is unavailable or unreadable."
        raise ToolError(msg) from None
    if size == 0:
        msg = "Textual witness files must not be empty."
        raise ToolError(msg)


async def validate_witness_file(path: Path, *, standalone: bool) -> None:
    """Stream local validation off the event loop before any upload mutation."""
    await anyio.to_thread.run_sync(partial(_validate_file, path, standalone=standalone))
