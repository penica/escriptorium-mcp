"""Resolve advertised model files without accepting arbitrary download targets."""

from typing import Final
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from mcp.server.mcpserver.exceptions import ToolError

from escriptorium_mcp.model_models import ModelRecord

CONTROL_LIMIT: Final = 32


def model_file_url(model: ModelRecord, site_url: str, revision: str | None) -> str:
    """Resolve current/checkpoint files and reject ambiguous or unsafe media paths."""
    if not model.file:
        message = "The model does not advertise a current file or media prefix."
        raise ToolError(message)
    raw_current_path = unquote(urlsplit(model.file).path)
    if (
        any(part in {".", ".."} for part in raw_current_path.split("/"))
        or any(character in raw_current_path for character in "\\%")
        or any(
            ord(character) < CONTROL_LIMIT
            for character in model.file + raw_current_path
        )
    ):
        message = "Unsafe model file path."
        raise ToolError(message)
    current = urlsplit(urljoin(site_url, model.file))
    site = urlsplit(site_url)
    if (
        current.scheme not in {"http", "https"}
        or (current.scheme, current.netloc) != (site.scheme, site.netloc)
        or current.username is not None
        or current.password is not None
        or current.fragment
        or current.query
    ):
        message = (
            "Model files must use the configured origin without credentials or query."
        )
        raise ToolError(message)
    decoded_path = unquote(current.path)
    if revision is None:
        return current.geturl()
    versions = [item for item in model.versions if item.revision == revision]
    if len(versions) != 1:
        message = "Revision must identify exactly one advertised checkpoint."
        raise ToolError(message)
    raw_path = versions[0].data.file
    if not raw_path:
        message = "The selected checkpoint does not advertise a file."
        raise ToolError(message)
    path = unquote(raw_path)
    parts = path.split("/")
    if (
        not path.startswith("models/")
        or any(part in {"", ".", ".."} for part in parts)
        or any(character in path for character in "\\?#:%")
        or any(ord(character) < CONTROL_LIMIT for character in path)
    ):
        message = "Unsafe checkpoint storage path."
        raise ToolError(message)
    if decoded_path.count("/models/") != 1:
        message = "Cannot determine an unambiguous model media prefix."
        raise ToolError(message)
    prefix = decoded_path.split("/models/", 1)[0] + "/"
    return urlunsplit(
        (current.scheme, current.netloc, quote(prefix + path, safe="/"), "", "")
    )
