"""Tiny in-memory TTL cache for owner portfolio queries."""
from __future__ import annotations

import time
from typing import Any

_STORE: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Any | None:
    item = _STORE.get(key)
    if not item:
        return None
    expires, value = item
    if time.time() > expires:
        _STORE.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl_seconds: float = 600) -> None:
    _STORE[key] = (time.time() + ttl_seconds, value)


def clear() -> None:
    _STORE.clear()
