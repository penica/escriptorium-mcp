import anyio

from escriptorium_mcp.server import create_server


def test_tools_when_server_is_created() -> None:
    # Given a configured MCP server factory.
    server = create_server()
    # When a client discovers tools.
    tools = anyio.run(server.list_tools)
    # Then document and transcription operations are available.
    assert {"list_documents", "get_page", "create_transcription"} <= {
        tool.name for tool in tools
    }
