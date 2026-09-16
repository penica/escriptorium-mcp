"""Version-dependent native ontology endpoints and byte-preserving YAML transfer."""

import json
from http import HTTPStatus
from pathlib import Path
from typing import Final, Literal, assert_never

from escriptorium_connector import EscriptoriumConnector
from escriptorium_connector.connector_errors import EscriptoriumConnectorHttpError
from exports import completed_file, destination_path
from pydantic import BaseModel, Field
from rest import ApiRequest, execute_api, same_origin
from storage import finish_file

MAX_BYTES: Final = 16 * 1024 * 1024


class NativeRequest(BaseModel):
    """Private native action with a derived same-origin endpoint."""

    operation: Literal["ontology_native"]
    action: Literal["capabilities", "export", "import"]
    scope: Literal["documents", "projects"]
    resource_id: int = Field(gt=0)
    file_path: Path | None = None
    destination: Path | None = None

    class Config:
        """Reject extra private request fields."""

        extra = "forbid"
        frozen = True


class Endpoint(BaseModel):
    """OPTIONS evidence; a hidden endpoint cannot be distinguished from absent."""

    status: Literal["available", "denied", "unavailable_or_hidden", "unknown"]
    http_status: int
    methods: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


def probe(client: EscriptoriumConnector, route: str) -> Endpoint:
    """Preserve denial versus missing-endpoint evidence without exposing bodies."""
    try:
        response = client.http.options(
            same_origin(client, client.api_url + route), allow_redirects=False
        )
    except EscriptoriumConnectorHttpError as error:
        response = error.error.response
    status = response.status_code
    if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        return Endpoint(status="denied", http_status=status)
    if status == HTTPStatus.NOT_FOUND:
        return Endpoint(status="unavailable_or_hidden", http_status=status)
    if not HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
        return Endpoint(status="unknown", http_status=status)
    data = response.json()
    fields = sorted(
        {key for values in data.get("actions", {}).values() for key in values}
    )
    return Endpoint(
        status="available",
        http_status=status,
        methods=[
            value.strip()
            for value in response.headers.get("Allow", "").split(",")
            if value.strip()
        ],
        fields=fields,
    )


def native_export(client: EscriptoriumConnector, request: NativeRequest) -> str:
    """Stream bounded YAML bytes with no redirect, overwrite, or JSON conversion."""
    if request.destination is None:
        msg = "A destination is required."
        raise ValueError(msg)
    destination = destination_path(request.destination)
    temporary = destination.with_name(destination.name + ".part")
    route = f"{request.scope}/{request.resource_id}/ontology/export/"
    with client.http.get(
        same_origin(client, client.api_url + route),
        stream=True,
        allow_redirects=False,
        headers={"Accept-Encoding": "identity"},
    ) as response:
        if response.is_redirect:
            msg = "Unexpected ontology export redirect."
            raise ValueError(msg)
        response.raise_for_status()
        total = 0
        with temporary.open("xb") as output:
            for chunk in response.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > MAX_BYTES:
                    msg = "Ontology export exceeds 16 MiB."
                    raise ValueError(msg)
                _ = output.write(chunk)
        expected = response.headers.get("Content-Length")
        if (
            expected
            and not response.headers.get("Content-Encoding")
            and total != int(expected)
        ):
            msg = "Ontology export byte count differs from Content-Length."
            raise ValueError(msg)
    finish_file(temporary, destination)
    return completed_file(destination)


def execute_native(client: EscriptoriumConnector, request: NativeRequest) -> str:
    """Check the parent resource first so missing records stay HTTP failures."""
    base = f"{request.scope}/{request.resource_id}/"
    _ = execute_api(client, ApiRequest(operation="api", method="GET", route=base))
    routes = {"export": base + "ontology/export/", "import": base + "ontology/import/"}
    if request.scope == "projects":
        routes["ontology"] = base + "ontology/"
    match request.action:
        case "capabilities":
            endpoints = {
                key: probe(client, route).dict() for key, route in routes.items()
            }
            return json.dumps(
                {
                    "scope": request.scope,
                    "resource_id": request.resource_id,
                    "endpoints": endpoints,
                    "types": {
                        kind: probe(client, f"types/{kind}/").dict()
                        for kind in ("block", "line", "part", "annotations")
                    },
                }
            )
        case "export" | "import":
            evidence = probe(client, routes[request.action])
            method = "GET" if request.action == "export" else "POST"
            if evidence.status != "available" or method not in evidence.methods:
                return json.dumps(
                    {
                        "status": "unavailable",
                        "action": request.action,
                        "capability": evidence.dict(),
                        "changed": False,
                    }
                )
            if request.action == "export":
                return native_export(client, request)
            if request.file_path is None:
                msg = "An ontology file is required."
                raise ValueError(msg)
            if request.file_path.stat().st_size > MAX_BYTES:
                msg = "Ontology import exceeds 16 MiB."
                raise ValueError(msg)
            return execute_api(
                client,
                ApiRequest(
                    operation="api",
                    method="POST",
                    route=routes["import"],
                    file_path=request.file_path,
                    file_field="file",
                ),
            )
        case unreachable:
            assert_never(unreachable)
