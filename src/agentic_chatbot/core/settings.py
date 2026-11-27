"""
Application settings.

Two sources, each with a clear job:

* Environment variables (and ``.env``) hold secrets and deployment details:
  API keys, database URLs, CORS origins, auth keys, rate limits.
* ``config/config.yaml`` holds model and pipeline tuning (providers, model
  names, RAG parameters, agent limits). Values in the YAML may reference
  environment variables with ``${VAR}`` or ``${VAR:-default}``.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

# Names of the variables that were put into os.environ from .env (rather than
# set by the real environment). Kept in the environment itself so the dev
# server's reloader child process, which inherits os.environ, still knows which
# values came from the file and may be refreshed when the file changes.
_OWNED_ENV = "JUNCTION_DOTENV_KEYS"


def _owned_keys() -> set[str]:
    return {k for k in os.environ.get(_OWNED_ENV, "").split(",") if k}


def load_env_file() -> None:
    """Apply ``.env`` to ``os.environ``.

    Variables set by the real environment (shell, Docker, Render) always win,
    as before. Variables that came from ``.env`` are updated when the file
    changes, and removed when they are deleted from it.
    """
    values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    owned = _owned_keys()
    for key in list(owned):
        if key not in values:
            os.environ.pop(key, None)
            owned.discard(key)
    for key, value in values.items():
        if value is None:
            continue
        if key in os.environ and key not in owned:
            continue  # set by the real environment
        os.environ[key] = value
        owned.add(key)
    os.environ[_OWNED_ENV] = ",".join(sorted(owned))


def _watched_files() -> list[Path]:
    config = Path(os.environ.get("CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    return [ENV_FILE, config]


def _fingerprint() -> tuple[int, ...]:
    stamps = []
    for path in _watched_files():
        try:
            stamps.append(path.stat().st_mtime_ns)
        except OSError:
            stamps.append(0)
    return tuple(stamps)


# Load .env early so that YAML ${VAR} expansion sees the same values.
load_env_file()
_watch_state: tuple[int, ...] | None = _fingerprint()
_watch_lock = threading.Lock()

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``${VAR:-default}`` inside YAML values."""
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, str):

        def _sub(match: re.Match) -> str:
            name, default = match.group(1), match.group(2)
            env = os.getenv(name)
            if env is None or env == "":
                return default if default is not None else ""
            return env

        expanded = _ENV_PATTERN.sub(_sub, value)
        # Keep YAML-style typing for whole-value substitutions ("0.3" -> 0.3).
        if expanded != value and _ENV_PATTERN.fullmatch(value.strip()):
            try:
                return yaml.safe_load(expanded) if expanded != "" else None
            except yaml.YAMLError:
                return expanded
        return expanded
    return value


class Settings(BaseSettings):
    """Environment-driven settings. See ``.env.example`` for documentation."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = Field("development", description="development | production")
    app_name: str = "Reittiä"  # shown in the UI and to connected apps; APP_NAME in .env overrides it
    app_version: str = "2.5.0"

    # Paths
    config_path: Path = PROJECT_ROOT / "config" / "config.yaml"
    mcp_config_path: Path = PROJECT_ROOT / "config" / "mcp_servers.yaml"
    integrations_config_path: Path = PROJECT_ROOT / "config" / "integrations.yaml"
    workspace_dir: Path = PROJECT_ROOT / "workspace"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    # LLM override (otherwise config.yaml llm.active_provider)
    llm_provider: str | None = None

    # Databases
    db_uri: str | None = None
    vector_db_uri: str | None = None
    db_pool_size: int = 10

    # HTTP
    allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    )
    api_keys: str = ""  # comma separated; empty disables auth
    rate_limit_per_minute: int = 30
    max_upload_mb: int = 25
    max_message_chars: int = 16000
    serve_frontend: bool = True

    # Features
    enable_mcp: bool = True
    # Adding local (stdio) MCP servers from the Connections panel runs a command on this machine.
    # Unset = allowed in development, refused in production.
    allow_ui_stdio: bool | None = None

    # Logging
    log_level: str = "INFO"
    log_format: str = ""  # "json" | "text"; default depends on environment
    log_file: str = ""

    @field_validator("db_uri", "vector_db_uri", "llm_provider", "allow_ui_stdio", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def ui_stdio_allowed(self) -> bool:
        return self.allow_ui_stdio if self.allow_ui_stdio is not None else not self.is_production

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def effective_vector_db_uri(self) -> str | None:
        return self.vector_db_uri or self.db_uri

    @property
    def uploads_dir(self) -> Path:
        return self.workspace_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_app_config() -> dict[str, Any]:
    """Load ``config/config.yaml`` with environment expansion."""
    path = get_settings().config_path
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return expand_env(raw)


def config_section(name: str) -> dict[str, Any]:
    return dict(get_app_config().get(name) or {})


def reset_caches() -> None:
    """Used by tests after changing environment variables."""
    get_settings.cache_clear()
    get_app_config.cache_clear()


def reload_if_changed(force: bool = False) -> bool:
    """Re-read ``.env`` and ``config.yaml`` if either was saved since the last check.

    Settings used to be read once at startup, so editing ``.env`` (for example
    switching ``LLM_PROVIDER``) did nothing until the server was restarted, and
    the UI kept reporting the old model as "not configured". This costs two
    ``stat`` calls, so it is cheap enough to call on every request.
    Returns True when the configuration was reloaded.
    """
    global _watch_state
    current = _fingerprint()
    if not force and current == _watch_state:
        return False
    with _watch_lock:
        if not force and current == _watch_state:
            return False
        load_env_file()
        reset_caches()
        _watch_state = current
    logger.info("Configuration reloaded from .env / config.yaml")
    return True


def pg_conninfo(uri: str) -> str:
    """psycopg wants a plain postgresql:// URI."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", uri)


def sqlalchemy_uri(uri: str) -> str:
    """langchain-postgres (SQLAlchemy) needs the psycopg3 driver spelled out."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg://", uri)
