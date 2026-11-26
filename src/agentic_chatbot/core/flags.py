"""Read on/off settings from config.yaml, where YAML turns a bare ``on``/``off``/``yes`` into a bool."""

from __future__ import annotations

from typing import Any

_TRUE = {"1", "true", "yes", "on", "enabled"}
_FALSE = {"0", "false", "no", "off", "disabled", "none", ""}


def as_flag(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default
