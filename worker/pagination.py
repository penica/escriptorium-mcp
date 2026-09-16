"""Guard and annotate a single native pagination response."""

from typing import TypeAlias
from urllib.parse import parse_qs, urlsplit

from escriptorium_connector import EscriptoriumConnector
from url_guard import scoped_next_url

JsonValue: TypeAlias = (
    str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
)
CANONICAL_FIRST_PREVIOUS_FROM_PAGE = 2
MAX_NATIVE_PAGE_SIZE = 50


def validate_native_request(
    method: str, query: dict[str, str], *, paginate: bool
) -> None:
    """Reject malformed private pagination fields before authenticated HTTP."""
    if method != "GET" or paginate:
        msg = "Native page selection requires a single GET request."
        raise ValueError(msg)
    page = query.get("page", "")
    page_size = query.get("paginate_by")
    if not page.isdigit() or int(page) < 1:
        msg = "Native page selection requires one positive numeric page."
        raise ValueError(msg)
    if page_size is not None and (
        not page_size.isdigit() or not 1 <= int(page_size) <= MAX_NATIVE_PAGE_SIZE
    ):
        msg = "Native page size must be between 1 and 50."
        raise ValueError(msg)


def _continuation_page(
    client: EscriptoriumConnector,
    initial_url: str,
    link: JsonValue,
    context: tuple[dict[str, str], int, bool],
) -> int | None:
    query, requested_page, forward = context
    if link is None:
        return None
    if not isinstance(link, str):
        msg = "Pagination continuation must be a URL string or null."
        raise TypeError(msg)
    absolute = scoped_next_url(client, initial_url, link)
    values = parse_qs(urlsplit(absolute).query, keep_blank_values=True)
    page_values = values.pop("page", [])
    canonical_first = (
        not page_values
        and not forward
        and requested_page == CANONICAL_FIRST_PREVIOUS_FROM_PAGE
    )
    if canonical_first:
        page = 1
    elif len(page_values) == 1 and page_values[0].isdigit():
        page = int(page_values[0])
    else:
        msg = "Pagination continuation has no single positive numeric page."
        raise ValueError(msg)
    expected = {key: [value] for key, value in query.items() if key != "page"}
    if page < 1 or values != expected:
        msg = "Pagination continuation changes the requested query."
        raise ValueError(msg)
    if page == requested_page or (forward and page < requested_page):
        msg = "Pagination continuation loops or reverses direction."
        raise ValueError(msg)
    if not forward and page > requested_page:
        msg = "Pagination continuation loops or reverses direction."
        raise ValueError(msg)
    return page


def annotate_native_page(
    client: EscriptoriumConnector,
    initial_url: str,
    data: JsonValue,
    query: dict[str, str],
) -> dict[str, JsonValue]:
    """Validate both links and add honest page-scoped metadata."""
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        msg = "Requested route does not return a native paginated envelope."
        raise TypeError(msg)
    requested_page = int(query["page"])
    forward = (query, requested_page, True)
    backward = (query, requested_page, False)
    next_page = _continuation_page(
        client,
        initial_url,
        data.get("next"),
        forward,
    )
    previous_page = _continuation_page(
        client,
        initial_url,
        data.get("previous"),
        backward,
    )
    count = data.get("count")
    native_total = (
        count
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0
        else None
    )
    output = dict(data)
    output["pagination"] = {
        "mode": "native_page",
        "page": requested_page,
        "page_size": int(query["paginate_by"]) if "paginate_by" in query else None,
        "returned_count": len(data["results"]),
        "native_total": native_total,
        "native_total_scope": "collection" if native_total is not None else "unknown",
        "filtered_total": None,
        "filtered_total_scope": "not_filtered",
        "has_next": next_page is not None,
        "has_previous": previous_page is not None,
        "next_page": next_page,
        "previous_page": previous_page,
        "collection_consistency": "snapshot_not_guaranteed",
    }
    return output
