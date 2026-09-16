"""Portable process entry point for local and private remote MCP clients."""

from enum import StrEnum
from typing import Annotated

import typer
import uvicorn

from escriptorium_mcp.settings import load_settings
from escriptorium_mcp.transport import http_app


class Transport(StrEnum):
    """Supported current MCP transports."""

    STDIO = "stdio"
    HTTP = "streamable-http"


def serve(
    transport: Annotated[
        Transport, typer.Option(help="Local subprocess or HTTP service.")
    ] = Transport.STDIO,
    host: Annotated[str, typer.Option(help="HTTP bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    allowed_host: Annotated[
        list[str] | None,
        typer.Option(help="Repeat for each permitted Host header, including port."),
    ] = None,
    allowed_origin: Annotated[
        list[str] | None,
        typer.Option(
            help="Repeat for trusted browser origins, including scheme and port."
        ),
    ] = None,
) -> None:
    """Serve eScriptorium tools; STDIO is the default."""
    from escriptorium_mcp.registry import create_server  # noqa: PLC0415

    server = create_server()
    if transport is Transport.STDIO:
        server.run(transport="stdio")
        return
    settings = load_settings()
    hosts = allowed_host or [f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]
    try:
        app = http_app(
            server, settings.http_token.get_secret_value(), hosts, allowed_origin or []
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Start the cross-platform command-line interface."""
    typer.run(serve)
