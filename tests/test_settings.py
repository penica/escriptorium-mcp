from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from escriptorium_mcp.settings import Settings, load_settings, worker_environment


def test_explicit_dotenv_and_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "chosen.env"
    _ = env_file.write_text(
        """ESCRIPTORIUM_URL=http://127.0.0.1:8091/
ESCRIPTORIUM_API_KEY=file-credential
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ESCRIPTORIUM_ENV_FILE", str(env_file))
    monkeypatch.delenv("ESCRIPTORIUM_API_KEY", raising=False)
    monkeypatch.delenv("ESCRIPTORIUM_URL", raising=False)
    from_file = load_settings()
    assert from_file.api_key.get_secret_value() == "file-credential"
    monkeypatch.setenv("ESCRIPTORIUM_API_KEY", "environment-credential")
    overridden = load_settings()
    assert overridden.api_key.get_secret_value() == "environment-credential"
    assert str(overridden.url) == "http://127.0.0.1:8091/"
    assert "environment-credential" not in repr(overridden)
    assert "environment-credential" not in overridden.model_dump_json()


def test_missing_explicit_dotenv_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESCRIPTORIUM_ENV_FILE", str(tmp_path / "missing.env"))
    with pytest.raises(FileNotFoundError, match="ESCRIPTORIUM_ENV_FILE"):
        _ = load_settings()


def test_worker_cache_is_outside_install_and_tracks_lock(tmp_path: Path) -> None:
    worker = tmp_path / "installed" / "worker"
    worker.mkdir(parents=True)
    lock = worker / "uv.lock"
    _ = lock.write_text("first-lock", encoding="utf-8")
    settings = Settings(
        worker_dir=worker,
        worker_cache=tmp_path / "writable-cache",
        api_key=SecretStr("private-fixture-key"),
    )
    first = worker_environment(settings)
    second = worker_environment(settings)
    cache_path = Path(first["UV_PROJECT_ENVIRONMENT"])
    assert cache_path == Path(second["UV_PROJECT_ENVIRONMENT"])
    assert cache_path.parent == settings.worker_cache
    assert not cache_path.is_relative_to(worker)
    cache_path.mkdir(parents=True)
    _ = (cache_path / "writable").write_text("yes", encoding="utf-8")
    _ = lock.write_text("second-lock", encoding="utf-8")
    assert worker_environment(settings)["UV_PROJECT_ENVIRONMENT"] != str(cache_path)
    assert first["PYTHONIOENCODING"] == "utf-8"


def test_validation_errors_do_not_echo_secrets() -> None:
    secret = "private-fixture-key"  # noqa: S105
    with pytest.raises(ValidationError) as captured:
        _ = Settings.model_validate({"url": "invalid", "api_key": secret})
    assert secret not in str(captured.value)
