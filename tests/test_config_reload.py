"""Editing .env takes effect without restarting the server."""

import os

import pytest


def _touch(path, step: int) -> None:
    """Move the file's mtime forward so the change is seen even on coarse clocks."""
    stamp = path.stat().st_mtime_ns + step * 2_000_000_000
    os.utime(path, ns=(stamp, stamp))


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    from agentic_chatbot.core import settings

    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "ENV_FILE", path)
    monkeypatch.setenv("JUNCTION_DOTENV_KEYS", "")
    monkeypatch.setattr(settings, "_watch_state", None)
    for key in ("JUNCTION_TEST_FLAG", "LLM_PROVIDER", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield path
    # Leave nothing from the temporary file behind for other tests.
    path.write_text("", encoding="utf-8")
    settings.load_env_file()


def test_env_edits_apply_and_removed_keys_disappear(env_file):
    from agentic_chatbot.core.settings import reload_if_changed

    env_file.write_text("JUNCTION_TEST_FLAG=one\n", encoding="utf-8")
    assert reload_if_changed(force=True) is True
    assert os.environ["JUNCTION_TEST_FLAG"] == "one"
    assert reload_if_changed() is False  # nothing changed since

    env_file.write_text("JUNCTION_TEST_FLAG=two\n", encoding="utf-8")
    _touch(env_file, 1)
    assert reload_if_changed() is True
    assert os.environ["JUNCTION_TEST_FLAG"] == "two"

    env_file.write_text("# flag removed\n", encoding="utf-8")
    _touch(env_file, 2)
    reload_if_changed()
    assert "JUNCTION_TEST_FLAG" not in os.environ


def test_real_environment_still_wins_over_env_file(env_file, monkeypatch):
    from agentic_chatbot.core.settings import reload_if_changed

    monkeypatch.setenv("JUNCTION_TEST_FLAG", "from-shell")
    env_file.write_text("JUNCTION_TEST_FLAG=from-file\n", encoding="utf-8")
    reload_if_changed(force=True)
    assert os.environ["JUNCTION_TEST_FLAG"] == "from-shell"


def test_switching_provider_in_env_file_fixes_meta_without_restart(env_file, client):
    from agentic_chatbot.core.settings import reload_if_changed

    env_file.write_text("LLM_PROVIDER=claude\nANTHROPIC_API_KEY=\n", encoding="utf-8")
    reload_if_changed(force=True)
    meta = client.get("/api/meta").json()
    assert meta["llm_ready"] is False
    assert meta["model"]["provider"] == "claude"
    assert "ANTHROPIC_API_KEY" in meta["llm_error"]

    # The user fixes .env while the server keeps running.
    env_file.write_text("LLM_PROVIDER=demo\n", encoding="utf-8")
    _touch(env_file, 1)
    meta = client.get("/api/meta").json()
    assert meta["llm_ready"] is True
    assert meta["model"]["provider"] == "demo"
