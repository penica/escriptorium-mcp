"""Module entry point and public server factory."""

from escriptorium_mcp.cli import main
from escriptorium_mcp.registry import create_server

__all__ = ["create_server", "main"]

if __name__ == "__main__":
    main()
