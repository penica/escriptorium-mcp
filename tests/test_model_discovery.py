import anyio

from escriptorium_mcp.server import create_server


def test_model_management_tools_are_discoverable_without_credentials() -> None:
    server = create_server()
    names = {tool.name for tool in anyio.run(server.list_tools)}
    assert {
        "update_model",
        "replace_model_file",
        "delete_model",
        "list_model_versions",
        "download_model",
        "get_model_documents",
    } <= names
