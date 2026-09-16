"""Page response compatibility for current eScriptorium installations."""

import json
import re
from http import HTTPStatus
from typing import Literal
from urllib.parse import urljoin, urlsplit

from escriptorium_connector import EscriptoriumConnector
from pydantic import BaseModel, ConstrainedInt
from pydantic.json import pydantic_encoder
from rest import same_origin


class PositiveIdentifier(ConstrainedInt):
    """Strict positive identifier on the private worker boundary."""

    strict = True
    gt = 0


class PageOrder(ConstrainedInt):
    """Zero-based page position, distinct from a page identifier."""

    strict = True
    ge = 0


class PagesByOrderRequest(BaseModel):
    """Allow only the bounded page-order lookup operation."""

    operation: Literal["page_by_order"]
    document_id: PositiveIdentifier
    order: PageOrder

    class Config:
        """Reject unsupported private wire fields."""

        extra = "forbid"
        frozen = True


class PageOrderLookupError(ValueError):
    """The native lookup did not identify a page at the requested order."""


class Region(BaseModel):
    """Preserve embedded region fields, including newer locking metadata."""

    pk: int

    class Config:
        """Retain fields the legacy connector DTO does not know."""

        extra = "allow"
        frozen = True


class Page(BaseModel):
    """Preserve current page fields without requiring removed legacy fields."""

    pk: int
    regions: list[Region] | None = None

    class Config:
        """Keep additional server metadata in the serialized response."""

        extra = "allow"
        frozen = True


class PageList(BaseModel):
    """Paginated page metadata."""

    count: int
    next: str | None
    previous: str | None
    results: list[Page]

    class Config:
        """Preserve additional collection metadata during pagination."""

        extra = "allow"
        frozen = True


def page_response(client: EscriptoriumConnector, url: str) -> bytes:
    """Read authenticated page JSON without following redirects."""
    response = client.http.get(same_origin(client, url), allow_redirects=False)
    if HTTPStatus.MULTIPLE_CHOICES <= response.status_code < HTTPStatus.BAD_REQUEST:
        msg = "Unexpected page API redirect."
        raise ValueError(msg)
    return response.content


def read_page_by_order(
    client: EscriptoriumConnector, request: PagesByOrderRequest
) -> str:
    """Follow only the native same-document page-detail redirect, once."""
    prefix = f"{client.api_url}documents/{request.document_id}/parts/"
    response = client.http.get(
        same_origin(client, prefix + "byorder/"),
        params={"order": request.order},
        allow_redirects=False,
    )
    if response.status_code != HTTPStatus.FOUND:
        raise PageOrderLookupError
    location = response.headers.get("Location", "")
    if not location or any(char <= " " for char in location):
        msg = "Invalid page-order redirect location."
        raise ValueError(msg)
    target = same_origin(client, urljoin(prefix + "byorder/", location))
    parsed = urlsplit(target)
    expected_path = re.escape(urlsplit(prefix).path) + r"([1-9][0-9]*)/"
    route_match = re.fullmatch(expected_path, parsed.path)
    if (
        parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or "%" in location
        or "\\" in location
        or route_match is None
    ):
        msg = "Page-order redirect is outside the requested document detail route."
        raise ValueError(msg)
    page = Page.parse_raw(page_response(client, target))
    if page.pk != int(route_match.group(1)):
        msg = "Page-order detail identity does not match the redirect target."
        raise ValueError(msg)
    return page.json(ensure_ascii=False)


def read_pages(client: EscriptoriumConnector, document_id: int, page_id: int) -> str:
    """Use connector authentication and HTTP handling with current page schemas."""
    url = f"{client.api_url}documents/{document_id}/parts/"
    if page_id:
        return Page.parse_raw(page_response(client, f"{url}{page_id}/")).json(
            ensure_ascii=False
        )
    page = PageList.parse_raw(page_response(client, url))
    results = list(page.results)
    next_url = page.next
    visited = {url}
    while next_url:
        absolute = same_origin(client, next_url)
        if absolute in visited:
            msg = "Page pagination loop detected."
            raise ValueError(msg)
        visited.add(absolute)
        following = PageList.parse_raw(page_response(client, absolute))
        results.extend(following.results)
        next_url = following.next
    return page.copy(update={"next": None, "previous": None, "results": results}).json(
        ensure_ascii=False
    )


def read_regions(client: EscriptoriumConnector, document_id: int, page_id: int) -> str:
    """Read embedded regions without the removed legacy image field."""
    page = Page.parse_raw(read_pages(client, document_id, page_id))
    return json.dumps(page.regions, default=pydantic_encoder, ensure_ascii=False)
