"""Resolve owned witness media without forwarding credentials to other paths."""

from typing import Final
from urllib.parse import unquote, urljoin, urlsplit

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue, ValidationError

from escriptorium_mcp.witness_models import WitnessRecord

CONTROL_LIMIT: Final = 32
DELETE_CHARACTER: Final = 127


def witness_file_url(record: JsonValue, site_url: str) -> str:
    """Require one unambiguous witness storage path on the configured origin."""
    try:
        file = WitnessRecord.model_validate(record).file
    except ValidationError:
        msg = "Witness metadata does not contain a valid file reference."
        raise ToolError(msg) from None
    if not file:
        msg = "The witness does not advertise a file."
        raise ToolError(msg)
    if any(ord(char) < CONTROL_LIMIT or ord(char) == DELETE_CHARACTER for char in file):
        msg = "Unsafe witness file URL."
        raise ToolError(msg)
    try:
        raw = urlsplit(file)
        decoded = unquote(raw.path)
        if (
            any(char in file for char in "\\?#")
            or any(char in decoded for char in "\\%?#")
            or any(
                ord(char) < CONTROL_LIMIT or ord(char) == DELETE_CHARACTER
                for char in decoded
            )
            or any(part in {".", ".."} for part in decoded.split("/"))
            or decoded.count("/") != raw.path.count("/")
        ):
            msg = "Unsafe witness file path."
            raise ToolError(msg)
        current = urlsplit(urljoin(site_url, file))
        site = urlsplit(site_url)
        origin = (
            current.scheme,
            current.hostname,
            current.port
            if current.port is not None
            else (443 if current.scheme == "https" else 80),
        )
        configured = (
            site.scheme,
            site.hostname,
            site.port
            if site.port is not None
            else (443 if site.scheme == "https" else 80),
        )
        path = unquote(current.path)
        if (
            current.scheme not in {"http", "https"}
            or origin != configured
            or current.username is not None
            or current.password is not None
            or current.query
            or current.fragment
            or path.split("/").count("witnesses") != 1
            or "/witnesses/" not in path
            or any(not part for part in path.split("/")[1:])
        ):
            msg = (
                "Witness files require the configured origin "
                "and a witness storage path."
            )
            raise ToolError(msg)
    except ValueError:
        msg = "Invalid witness file URL."
        raise ToolError(msg) from None
    return current.geturl()
