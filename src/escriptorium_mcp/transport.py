"""Authenticated Streamable HTTP for a private, single-account MCP service."""

import secrets
from typing import Final

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MIN_TOKEN_LENGTH: Final = 32


class BearerAuth:
    """Require the service token before any HTTP request reaches MCP."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        """Keep the credential out of command-line arguments and access logs."""
        self.app: ASGIApp = app
        self.token: bytes = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass lifespan events through; authenticate HTTP requests."""
        if scope["type"] == "http":
            supplied = Headers(scope=scope).get("authorization", "").encode()
            if not secrets.compare_digest(supplied, self.token):
                response = PlainTextResponse(
                    "Unauthorized",
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def http_app(
    server: MCPServer,
    token: str,
    allowed_hosts: list[str],
    allowed_origins: list[str],
) -> Starlette:
    """Build a stateless endpoint with explicit Host/Origin validation."""
    if (
        len(token) < MIN_TOKEN_LENGTH
        or not token.isascii()
        or any(char.isspace() for char in token)
    ):
        msg = (
            "Set ESCRIPTORIUM_HTTP_TOKEN to at least 32 ASCII characters "
            "without spaces."
        )
        raise ValueError(msg)
    if not allowed_hosts or any("*" in host.split(":")[0] for host in allowed_hosts):
        msg = "Specify concrete allowed HTTP hostnames; wildcard hostnames are refused."
        raise ValueError(msg)
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )
    app.add_middleware(BearerAuth, token=token)
    return app
