import anyio

from escriptorium_mcp.server import create_server


def test_extended_tools_when_server_is_created() -> None:
    # Given the public MCP server.
    server = create_server()
    # When tools are discovered.
    names = {tool.name for tool in anyio.run(server.list_tools)}
    # Then all previously missing capability groups are present.
    assert {
        "create_document",
        "upload_page",
        "create_line_transcription",
        "update_line_transcription",
        "create_line",
        "update_region",
        "segment_pages",
        "transcribe_pages",
        "train_recognition",
        "train_segmentation",
        "export_transcriptions",
        "download_register",
        "rename_project",
        "update_document",
        "move_page",
        "delete_document",
    } <= names
