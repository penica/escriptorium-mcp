"""Authenticated URL guards shared by worker transports."""

from urllib.parse import urljoin, urlsplit

from escriptorium_connector import EscriptoriumConnector


def same_origin(client: EscriptoriumConnector, url: str) -> str:
    """Prevent authenticated requests from leaving the configured server."""
    absolute = urljoin(client.base_url, url)
    expected = urlsplit(client.base_url)
    actual = urlsplit(absolute)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        msg = "Cross-origin authenticated URL refused."
        raise ValueError(msg)
    return absolute


def scoped_next_url(
    client: EscriptoriumConnector, initial_url: str, next_url: str
) -> str:
    """Keep pagination inside the original authenticated collection route."""
    supplied = urlsplit(next_url)
    absolute = same_origin(client, urljoin(initial_url, next_url))
    parsed = urlsplit(absolute)
    if (
        any(char <= " " for char in next_url)
        or "\\" in next_url
        or "#" in next_url
        or "%" in supplied.path
        or any(segment in {".", ".."} for segment in supplied.path.split("/"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != urlsplit(initial_url).path
    ):
        msg = "Pagination leaves the original collection route."
        raise ValueError(msg)
    return absolute
