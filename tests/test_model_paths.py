import pytest
from mcp.server.mcpserver.exceptions import ToolError

from escriptorium_mcp.model_files import model_file_url
from escriptorium_mcp.model_models import ModelRecord


@pytest.mark.parametrize(
    "file",
    [
        "/media/models/../private.txt",
        "/media/models/%252e%252e/private.txt",
        "/media/models/file\n.safetensors",
        "/media/models/file%00.safetensors",
    ],
)
def test_current_file_path_is_checked_before_url_normalization(file: str) -> None:
    model = ModelRecord(pk=1, file=file)
    with pytest.raises(ToolError):
        _ = model_file_url(model, "http://fixture/", None)


def test_checkpoint_retains_reverse_proxy_prefix_and_quotes_filename() -> None:
    model = ModelRecord.model_validate(
        {
            "pk": 1,
            "file": "http://fixture/escriptorium/media/models/abc/current.safetensors",
            "versions": [
                {"revision": "first", "data": {"file": "models/abc/epoch=1 test.ckpt"}}
            ],
        }
    )
    assert model_file_url(model, "http://fixture/escriptorium/", "first") == (
        "http://fixture/escriptorium/media/models/abc/epoch%3D1%20test.ckpt"
    )
