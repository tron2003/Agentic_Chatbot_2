"""
Start a local Ollama when it isn't running.

Uploads failed with "Couldn't reach Ollama" whenever Ollama wasn't open, which
on Windows happens after every restart unless the tray app auto-starts. In
development, when ``embeddings.ollama.base_url`` points at this machine and the
``ollama`` program is installed, the server now starts ``ollama serve`` itself
and waits a few seconds for it. Production never starts processes.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from agentic_chatbot.core.flags import as_flag
from agentic_chatbot.core.settings import config_section, get_settings

logger = logging.getLogger(__name__)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
START_TIMEOUT_SECONDS = 20.0
_lock = threading.Lock()
_started_at: float | None = None


def _target(base_url: str) -> tuple[str, int]:
    parts = urlsplit(base_url)
    return parts.hostname or "127.0.0.1", parts.port or 11434


def is_reachable(base_url: str, timeout: float = 0.5) -> bool:
    host, port = _target(base_url)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    if sys.platform == "win32":  # the Windows installer doesn't always add itself to PATH
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _autostart_enabled() -> bool:
    block = config_section("embeddings").get("ollama") or {}
    return as_flag(block.get("autostart"), default=True) and not get_settings().is_production


def ensure_ollama(base_url: str) -> bool:
    """True when Ollama answers at ``base_url``, starting it first if allowed. Blocking: run in a thread."""
    global _started_at
    if is_reachable(base_url):
        return True
    host, _ = _target(base_url)
    if host not in LOCAL_HOSTS or not _autostart_enabled():
        return False
    exe = find_ollama()
    if not exe:
        logger.info("Ollama isn't running and the ollama program wasn't found, so it can't be started")
        return False

    with _lock:
        if not is_reachable(base_url) and (_started_at is None or time.monotonic() - _started_at > START_TIMEOUT_SECONDS):
            logger.warning("Ollama isn't running at %s; starting `ollama serve`", base_url)
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            try:
                subprocess.Popen(  # noqa: S603 - fixed program path, no shell
                    [exe, "serve"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    start_new_session=sys.platform != "win32",
                )
            except OSError as exc:
                logger.error("Couldn't start Ollama: %s", exc)
                return False
            _started_at = time.monotonic()

    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if is_reachable(base_url):
            logger.info("Ollama is up at %s", base_url)
            return True
        time.sleep(0.4)
    return False
