"""The model chosen in the UI's model picker.

Saved as JSON (``config/model_selection.json`` by default, ``MODEL_SELECTION_PATH``
to move it) so it survives restarts. While it exists it overrides
``LLM_PROVIDER`` / ``ROUTER_PROVIDER`` and the model names from .env and
config.yaml; "Reset to .env" in the UI deletes it.

    {"main": {"provider": "openrouter", "model": "openai/gpt-oss-20b:free"},
     "router": null}                      # null = route with the main model
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_chatbot.core.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

PROVIDERS = ("openrouter", "ollama", "claude", "openai", "local", "demo")

_lock = threading.Lock()
_cache: tuple[str, int, dict[str, Any] | None] | None = None  # (path, mtime_ns, data)


def selection_path() -> Path:
    return Path(os.environ.get("MODEL_SELECTION_PATH") or PROJECT_ROOT / "config" / "model_selection.json")


def _valid_choice(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    provider = str(value.get("provider") or "").strip().lower()
    model = str(value.get("model") or "").strip()
    if provider not in PROVIDERS:
        return None
    return {"provider": provider, "model": model}


def load_selection() -> dict[str, Any] | None:
    """The saved choice, or None. Re-read only when the file changes."""
    global _cache
    path = selection_path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    if _cache and _cache[0] == str(path) and _cache[1] == mtime:
        return _cache[2]
    data: dict[str, Any] | None = None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        main = _valid_choice(raw.get("main"))
        if main:
            data = {"main": main, "router": _valid_choice(raw.get("router"))}
        else:
            logger.warning("Ignoring %s: it has no valid main model", path)
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning("Ignoring unreadable model selection %s: %s", path, exc)
    with _lock:
        _cache = (str(path), mtime, data)
    return data


def save_selection(main: dict[str, str], router: dict[str, str] | None) -> dict[str, Any]:
    data = {"main": main, "router": router, "updated_at": datetime.now(UTC).isoformat()}
    path = selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)  # atomic, so a reader never sees half a file
    logger.info("Model selection saved: main=%s/%s router=%s", main["provider"], main["model"],
                f"{router['provider']}/{router['model']}" if router else "same as main")
    return data


def clear_selection() -> bool:
    path = selection_path()
    with _lock:
        try:
            path.unlink()
        except FileNotFoundError:
            return False
    logger.info("Model selection cleared; using .env / config.yaml")
    return True
