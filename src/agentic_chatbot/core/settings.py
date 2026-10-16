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

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load .env early so that YAML ${VAR} expansion sees the same values.
load_dotenv(PROJECT_ROOT / ".env", override=False)

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
    app_name: str = "Junction"
    app_version: str = "2.1.0"

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

    # Logging
    log_level: str = "INFO"
    log_format: str = ""  # "json" | "text"; default depends on environment
    log_file: str = ""

    @field_validator("db_uri", "vector_db_uri", "llm_provider", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

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


def pg_conninfo(uri: str) -> str:
    """psycopg wants a plain postgresql:// URI."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", uri)


def sqlalchemy_uri(uri: str) -> str:
    """langchain-postgres (SQLAlchemy) needs the psycopg3 driver spelled out."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg://", uri)
