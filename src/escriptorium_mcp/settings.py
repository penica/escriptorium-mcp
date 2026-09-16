"""Configuration and writable worker locations on each supported platform."""

import hashlib
import os
from pathlib import Path
from typing import ClassVar, Final

from platformdirs import user_cache_path
from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BUNDLED_WORKER: Final = Path(__file__).with_name("worker")
SOURCE_ROOT: Final = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Load secrets from the environment or an explicitly selected dotenv file."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="ESCRIPTORIUM_",
        frozen=True,
        hide_input_in_errors=True,
        extra="ignore",
    )
    url: HttpUrl | None = None
    api_key: SecretStr = SecretStr("")
    username: str = ""
    password: SecretStr = SecretStr("")
    books_root: Path | None = None
    worker_dir: Path = (
        BUNDLED_WORKER if BUNDLED_WORKER.is_dir() else SOURCE_ROOT / "worker"
    )
    worker_cache: Path = (
        user_cache_path("escriptorium-mcp", appauthor=False) / "workers"
    )
    http_token: SecretStr = SecretStr("")


def load_settings() -> Settings:
    """Prefer a chosen file; source checkouts retain their local dotenv discovery."""
    chosen = os.environ.get("ESCRIPTORIUM_ENV_FILE")
    env_file = Path(chosen).expanduser() if chosen else SOURCE_ROOT / ".env"
    if chosen and not env_file.is_file():
        msg = "ESCRIPTORIUM_ENV_FILE does not point to an existing file."
        raise FileNotFoundError(msg)

    class FileSettings(Settings):
        model_config: ClassVar[SettingsConfigDict] = {
            **Settings.model_config,
            "env_file": env_file if chosen or not BUNDLED_WORKER.is_dir() else None,
        }

    return FileSettings()


def worker_environment(settings: Settings) -> dict[str, str]:
    """Keep the legacy runtime in a writable cache, independent of install location."""
    lock_hash = hashlib.sha256(
        (settings.worker_dir / "uv.lock").read_bytes()
    ).hexdigest()[:16]
    environment = dict(os.environ)
    environment.update(
        {
            "ESCRIPTORIUM_URL": str(settings.url),
            "ESCRIPTORIUM_API_KEY": settings.api_key.get_secret_value(),
            "ESCRIPTORIUM_USERNAME": settings.username,
            "ESCRIPTORIUM_PASSWORD": settings.password.get_secret_value(),
            "ESCRIPTORIUM_BOOKS_ROOT": str(settings.books_root.expanduser())
            if settings.books_root
            else "",
            "UV_PROJECT_ENVIRONMENT": str(
                settings.worker_cache.expanduser().resolve() / lock_hash
            ),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment
