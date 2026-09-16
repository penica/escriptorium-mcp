"""Additional REST actions through the connector's authenticated HTTP session."""

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

from escriptorium_connector import EscriptoriumConnector
from pydantic import BaseModel, Field


class ApiRequest(BaseModel):
    """Private request from explicitly registered MCP tools."""

    operation: Literal["api"]
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    route: str = Field(
        regex=r"^(documents|projects|models|scripts|tasks|types)/[a-z0-9_/]*$"
    )
    body_json: str = "{}"
    file_path: Path | None = None
    file_field: Literal["image", "file", "upload_file"] = "image"
    paginate: bool = False
    query: dict[str, str] = Field(default_factory=dict)

    class Config:
        """Enforce the private message contract."""

        extra = "forbid"
        frozen = True


def same_origin(client: EscriptoriumConnector, url: str) -> str:
    """Prevent pagination links from forwarding an API token to another server."""
    absolute = urljoin(client.base_url, url)
    expected = urlsplit(client.base_url)
    actual = urlsplit(absolute)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        msg = "Cross-origin authenticated URL refused."
        raise ValueError(msg)
    return absolute


def execute_api(client: EscriptoriumConnector, request: ApiRequest) -> str:
    """Perform one action, preserving server JSON and bodyless success responses."""
    url = client.api_url + request.route
    body = json.loads(request.body_json)
    if request.route.endswith("/export/") and "region_types" not in body:
        document_id = int(request.route.split("/")[1])
        body["region_types"] = [
            region.pk for region in client.get_document_region_types(document_id)
        ] + ["Undefined", "Orphan"]
    if request.file_path is not None:
        with request.file_path.open("rb") as uploaded:
            response = client.http.request(
                request.method,
                url,
                data=body,
                files={request.file_field: (request.file_path.name, uploaded)},
                allow_redirects=False,
            )
    else:
        response = client.http.request(
            request.method,
            url,
            json=body if request.method not in {"GET", "OPTIONS"} else None,
            params=request.query,
            allow_redirects=False,
        )
    if response.is_redirect:
        msg = "Unexpected API redirect."
        raise ValueError(msg)
    if not response.content:
        return json.dumps({"status": "success", "http_status": response.status_code})
    if request.paginate:
        data = response.json()
        if isinstance(data, list):
            return json.dumps(data, ensure_ascii=False)
        next_url = data.get("next")
        visited = {url}
        while next_url:
            absolute = same_origin(client, next_url)
            if absolute in visited:
                msg = "Pagination loop detected."
                raise ValueError(msg)
            visited.add(absolute)
            following = client.http.get(absolute, allow_redirects=False)
            following.raise_for_status()
            page = following.json()
            data["results"].extend(page["results"])
            next_url = page.get("next")
        data["next"] = None
        return json.dumps(data, ensure_ascii=False)
    return response.text
