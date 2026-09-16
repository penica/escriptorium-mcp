"""Fixed-route generated downloads with bounded pagination and file publication."""

import json
from http import HTTPStatus
from typing import assert_never
from urllib.parse import urlencode, urljoin, urlsplit

from download_models import (
    DownloadAction,
    DownloadDetail,
    DownloadFile,
    DownloadFileRecord,
    DownloadPage,
    DownloadRecord,
    Fingerprint,
    ListDownloads,
    PageSelection,
)
from escriptorium_connector import EscriptoriumConnector
from exports import completed_file, destination_path
from pagination import annotate_native_page
from pydantic import parse_raw_as
from pydantic.json import pydantic_encoder
from requests import Response
from rest import same_origin
from storage import finish_file


def require_success(response: Response) -> None:
    """Refuse every redirect and propagate HTTP errors even for empty bodies."""
    if HTTPStatus.MULTIPLE_CHOICES <= response.status_code < HTTPStatus.BAD_REQUEST:
        msg = "Download API redirect refused."
        raise ValueError(msg)
    response.raise_for_status()


def collection_url(client: EscriptoriumConnector, next_url: str) -> str:
    """Resolve pagination only inside the configured downloads collection."""
    collection = client.api_url + "downloads/"
    supplied = urlsplit(next_url)
    absolute = same_origin(client, urljoin(collection, next_url))
    parsed = urlsplit(absolute)
    if (
        any(char <= " " for char in next_url)
        or "\\" in next_url
        or "#" in next_url
        or "%" in supplied.path
        or any(segment in {".", ".."} for segment in supplied.path.split("/"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != urlsplit(collection).path
    ):
        msg = "Download pagination leaves the configured collection route."
        raise ValueError(msg)
    return absolute


def read_downloads(
    client: EscriptoriumConnector, pagination: PageSelection | None
) -> str:
    """Preserve legacy collection reads or return one guarded native page."""
    collection = client.api_url + "downloads/"
    query = {"page": str(pagination.page)} if pagination is not None else {}
    if pagination is not None and pagination.page_size is not None:
        query["paginate_by"] = str(pagination.page_size)
    url = collection_url(
        client, f"{collection}?{urlencode(query)}" if query else collection
    )
    with client.http.get(url, allow_redirects=False) as response:
        require_success(response)
        if pagination is not None:
            return json.dumps(
                annotate_native_page(client, collection, response.json(), query),
                ensure_ascii=False,
            )
        data = parse_raw_as(list[DownloadRecord] | DownloadPage, response.content)
    match data:
        case list():
            result = json.dumps(data, default=pydantic_encoder, ensure_ascii=False)
        case DownloadPage():
            records = list(data.results)
            next_url = data.next
            visited = {url}
            while next_url:
                absolute = collection_url(client, next_url)
                if absolute in visited:
                    msg = "Download pagination loop detected."
                    raise ValueError(msg)
                visited.add(absolute)
                with client.http.get(absolute, allow_redirects=False) as response:
                    require_success(response)
                    following = DownloadPage.parse_raw(response.content)
                records.extend(following.results)
                next_url = following.next
            result = data.copy(update={"next": None, "results": records}).json(
                exclude_unset=True, ensure_ascii=False
            )
        case unreachable:
            assert_never(unreachable)
    return result


def read_download(client: EscriptoriumConnector, fingerprint: Fingerprint) -> str:
    """Verify the returned identity while retaining all native metadata fields."""
    url = same_origin(client, f"{client.api_url}downloads/{fingerprint}/")
    with client.http.get(url, allow_redirects=False) as response:
        require_success(response)
        record = DownloadRecord.parse_raw(response.content)
    if record.fingerprint != fingerprint:
        msg = "Download metadata identifies a different artifact."
        raise ValueError(msg)
    return record.json(exclude_unset=True, ensure_ascii=False)


def download_file(client: EscriptoriumConnector, request: DownloadFile) -> str:
    """Stream only the fixed file route and verify size before publication."""
    metadata = DownloadFileRecord.parse_raw(read_download(client, request.fingerprint))
    destination = destination_path(request.destination)
    temporary = destination.with_name(destination.name + ".part")
    url = same_origin(client, f"{client.api_url}downloads/{request.fingerprint}/file/")
    with client.http.get(
        url, stream=True, allow_redirects=False, headers={"Accept-Encoding": "identity"}
    ) as response:
        require_success(response)
        with temporary.open("xb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                _ = output.write(chunk)
        size = temporary.stat().st_size
        if size != metadata.file_size:
            msg = "Download byte count differs from its advertised file size."
            raise ValueError(msg)
        length = response.headers.get("Content-Length")
        encoding = response.headers.get("Content-Encoding", "").strip().lower()
        if length is not None and encoding in {"", "identity"} and size != int(length):
            msg = "Download byte count differs from Content-Length."
            raise ValueError(msg)
    finish_file(temporary, destination)
    return completed_file(destination)


def delete_download(client: EscriptoriumConnector, request: DownloadDetail) -> str:
    """Send one native DELETE without treating row deletion as secure erasure."""
    url = same_origin(client, f"{client.api_url}downloads/{request.fingerprint}/")
    with client.http.delete(url, allow_redirects=False) as response:
        require_success(response)
        return response.text or json.dumps(
            {"status": "success", "http_status": response.status_code}
        )


def execute_downloads(client: EscriptoriumConnector, raw: str) -> str:
    """Parse a fixed action and suppress automatic repeat requests."""
    for adapter in client.http.adapters.values():
        adapter.max_retries = adapter.max_retries.new(
            total=0, connect=0, read=0, redirect=0, status=0, raise_on_status=False
        )
    match DownloadAction.parse_raw(raw).action:
        case "list":
            request = ListDownloads.parse_raw(raw)
            result = read_downloads(client, request.pagination)
        case "get":
            request = DownloadDetail.parse_raw(raw)
            result = read_download(client, request.fingerprint)
        case "delete":
            result = delete_download(client, DownloadDetail.parse_raw(raw))
        case "file":
            result = download_file(client, DownloadFile.parse_raw(raw))
        case unreachable:
            assert_never(unreachable)
    return result
