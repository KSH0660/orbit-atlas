"""Runtime settings, read from environment variables (see deploy/spec2kb.env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - config error path
        raise SystemExit(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("S2K_DATA_DIR", "./s2k-data")).resolve())
    host: str = field(default_factory=lambda: _env("S2K_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("S2K_PORT", 8765))
    max_upload_mb: int = field(default_factory=lambda: _env_int("S2K_MAX_UPLOAD_MB", 300))
    workers: int = field(default_factory=lambda: _env_int("S2K_WORKERS", 2))
    # "user:password" enables HTTP Basic auth for the UI and API
    basic_auth: str = field(default_factory=lambda: _env("S2K_BASIC_AUTH"))
    log_level: str = field(default_factory=lambda: _env("S2K_LOG_LEVEL", "INFO").upper())
    # Default CA bundle for provider HTTPS calls (internal PKI); empty = system default
    ca_bundle: str = field(default_factory=lambda: _env("S2K_CA_BUNDLE"))
    # Default provider id used by new profiles / when a profile names none
    default_provider: str = field(default_factory=lambda: _env("S2K_DEFAULT_PROVIDER", "mock"))
    # Optional JSON file with providers to seed on first start (for automated deployment)
    providers_seed: str = field(default_factory=lambda: _env("S2K_PROVIDERS_SEED"))
    preview_dpi: int = field(default_factory=lambda: _env_int("S2K_PREVIEW_DPI", 110))
    allow_api_key_storage: bool = field(
        default_factory=lambda: _env_bool("S2K_ALLOW_API_KEY_STORAGE", True))

    @property
    def docs_dir(self) -> Path:
        return self.data_dir / "docs"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def providers_file(self) -> Path:
        return self.data_dir / "providers.json"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.docs_dir, self.profiles_dir, self.cache_dir / "vision"):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Override settings (tests, CLI flags)."""
    global _settings
    _settings = settings
