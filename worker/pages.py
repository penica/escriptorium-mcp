"""Page response compatibility for current eScriptorium installations."""

import json

from escriptorium_connector import EscriptoriumConnector
from escriptorium_connector.dtos import GetRegion
from pydantic import BaseModel
from pydantic.json import pydantic_encoder


class Page(BaseModel):
    """Preserve current page fields without requiring removed legacy fields."""

    pk: int
    regions: list[GetRegion] | None = None

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


def read_pages(client: EscriptoriumConnector, document_id: int, page_id: int) -> str:
    """Use connector authentication and HTTP handling with current page schemas."""
    url = f"{client.api_url}documents/{document_id}/parts/"
    if page_id:
        response = client.http.get(f"{url}{page_id}/")
        return Page.parse_raw(response.content).json(ensure_ascii=False)
    page = PageList.parse_raw(client.http.get(url).content)
    results = list(page.results)
    next_url = page.next
    while next_url:
        following = PageList.parse_raw(client.http.get(next_url).content)
        results.extend(following.results)
        next_url = following.next
    return PageList(count=page.count, next=None, previous=None, results=results).json(
        ensure_ascii=False,
    )


def read_regions(client: EscriptoriumConnector, document_id: int, page_id: int) -> str:
    """Read embedded regions without the removed legacy image field."""
    page = Page.parse_raw(read_pages(client, document_id, page_id))
    return json.dumps(page.regions, default=pydantic_encoder, ensure_ascii=False)
