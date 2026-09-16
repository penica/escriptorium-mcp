import hashlib
import json
import shutil
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Final

import pytest
from pydantic import BaseModel
from typing_extensions import override

UV: Final = shutil.which("uv") or "uv"
WORKER: Final = Path(__file__).resolve().parents[1] / "worker"
SCRIPT: Final = """
import sys
from pathlib import Path
from archive import ArchiveRequest, download_register
from escriptorium_connector import EscriptoriumConnector
request = ArchiveRequest(operation='download_register', document_id=int(sys.argv[3]),
    parish='Test', register_id='02751', register_type='Baptisms', years='1838-1879')
client = EscriptoriumConnector(base_url=sys.argv[1], api_key='fixture-key')
with client.http:
    print(download_register(client, request, root=Path(sys.argv[2])))
"""


class FileEntry(BaseModel):
    original_filename: str
    local_filename: str
    sha256: str | None
    bytes: int


class SavedManifest(BaseModel):
    status: str
    downloaded_scans: int
    historical_missing_pages: str
    files: list[FileEntry] = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        assert self.headers.get("Authorization") == "Token fixture-key"
        if self.path.startswith("/media/"):
            if self.path.endswith("bad"):
                self.send_error(404)
                return
            body = self.path.encode()
        else:
            second = "page=2" in self.path
            page_id = 2 if second else 1
            image = f"/media/{page_id}"
            if "/documents/2/" in self.path and second:
                image = "/media/bad"
            if "/documents/3/" in self.path:
                image = "http://example.invalid/private"
            body = json.dumps(
                {
                    "count": 2,
                    "next": None if second else self.path + "?page=2",
                    "results": [
                        {
                            "pk": page_id,
                            "filename": "../same.jpg",
                            "image": {"uri": image},
                        }
                    ],
                }
            ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    @override
    def log_message(self, format: str, *args: str) -> None:
        return


@contextmanager
def fixture_api() -> Generator[str, None, None]:
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            thread.join()


def run_archive(
    url: str, root: Path, document: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            UV,
            "run",
            "--frozen",
            "--project",
            str(WORKER),
            "python",
            "-c",
            SCRIPT,
            url,
            str(root),
            str(document),
        ],
        cwd=WORKER,
        capture_output=True,
        text=True,
        check=False,
    )


def test_download_complete_inventory_and_refuse_overwrite(tmp_path: Path) -> None:
    with fixture_api() as url:
        result = run_archive(url, tmp_path, 1)
        assert result.returncode == 0, result.stderr
        folder = tmp_path / "Test/02751_Baptisms_1838-1879"
        manifest = SavedManifest.model_validate_json(
            (folder / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest.status == "complete_available_scans"
        assert manifest.downloaded_scans == 2
        assert manifest.historical_missing_pages.startswith("unknown")
        for item in manifest.files:
            assert item.original_filename == "../same.jpg"
            payload = (folder / item.local_filename).read_bytes()
            assert item.sha256 == hashlib.sha256(payload).hexdigest()
            assert item.bytes == len(payload)
        repeated = run_archive(url, tmp_path, 1)
        assert repeated.returncode != 0
        assert "FileExistsError" in repeated.stderr
        assert not list(folder.glob("*.part"))


@pytest.mark.parametrize("document", [2, 3])
def test_failed_download_or_unsafe_origin_remains_partial(
    tmp_path: Path,
    document: int,
) -> None:
    with fixture_api() as url:
        result = run_archive(url, tmp_path, document)
    assert result.returncode != 0
    manifest = SavedManifest.model_validate_json(
        (tmp_path / "Test/02751_Baptisms_1838-1879/manifest.json").read_text(
            encoding="utf-8"
        ),
    )
    assert manifest.status == "partial"
    assert manifest.downloaded_scans == (1 if document == 2 else 0)


@pytest.mark.parametrize("parish", ["CON", "nul.txt", "COM1", "Test.", "Test "])
def test_archive_rejects_windows_unsafe_parish(parish: str) -> None:
    script = (
        "from archive import ArchiveRequest; import sys; ArchiveRequest("
        "operation='download_register', document_id=1, parish=sys.argv[1], "
        "register_id='1', register_type='Baptisms', years='1900')"
    )
    result = subprocess.run(  # noqa: S603
        [
            UV,
            "run",
            "--frozen",
            "--project",
            str(WORKER),
            "python",
            "-c",
            script,
            parish,
        ],
        cwd=WORKER,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_storage_uses_explicit_root_and_preserves_conflicts(tmp_path: Path) -> None:
    script = """
import os
import sys
from pathlib import Path
from storage import books_root, finish_file, scan_filename
from exports import destination_path
root = Path(sys.argv[1])
os.environ.pop('ESCRIPTORIUM_BOOKS_ROOT', None)
assert books_root() is None
os.environ['ESCRIPTORIUM_BOOKS_ROOT'] = str(root)
assert books_root() == root
try:
    destination_path(root / 'forbidden.txt')
except ValueError:
    pass
else:
    raise AssertionError('export allowed inside scan archive')
os.environ['ESCRIPTORIUM_BOOKS_ROOT'] = 'relative/path'
try:
    books_root()
except ValueError:
    pass
else:
    raise AssertionError('relative archive root accepted')
os.environ['ESCRIPTORIUM_BOOKS_ROOT'] = str(root)
assert not scan_filename('trailing.').endswith('.')
assert len(scan_filename('č' * 200).encode('utf-8')) <= 160
source = root / 'export.part'
target = root / 'export'
source.write_bytes(b'new')
target.write_bytes(b'old')
try:
    finish_file(source, target)
except FileExistsError:
    pass
else:
    raise AssertionError('overwrote existing destination')
assert target.read_bytes() == b'old'
assert source.read_bytes() == b'new'
target.unlink()
os.link = lambda *args: (_ for _ in ()).throw(OSError('hardlinks unavailable'))
finish_file(source, target)
assert target.read_bytes() == b'new'
assert not source.exists()
source.write_bytes(b'retry')
target.unlink()
import shutil
def fail_copy(*args, **kwargs):
    raise OSError('fixture disk failure')
shutil.copyfileobj = fail_copy
try:
    finish_file(source, target)
except OSError:
    pass
else:
    raise AssertionError('copy failure ignored')
assert source.read_bytes() == b'retry'
assert not target.exists()
"""
    result = subprocess.run(  # noqa: S603
        [
            UV,
            "run",
            "--frozen",
            "--project",
            str(WORKER),
            "python",
            "-c",
            script,
            str(tmp_path),
        ],
        cwd=WORKER,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
