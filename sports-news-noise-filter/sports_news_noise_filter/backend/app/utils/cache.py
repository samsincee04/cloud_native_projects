"""In-memory TTL cache for GET /feed_clusters only."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def _ttl_seconds() -> float:
    try:
        raw = float(os.getenv("FEED_CACHE_TTL_SECONDS", "45"))
    except ValueError:
        raw = 45.0
    # Safe bounds (spec suggests ~30–60s typical)
    return max(5.0, min(120.0, raw))


def feed_clusters_cache_get(key: str) -> tuple[Any | None, float | None]:
    """
    Returns (value, age_s) on hit, (None, None) on miss or expiry.
    """
    now = time.time()
    ttl = _ttl_seconds()
    with _lock:
        row = _store.get(key)
        if row is None:
            return None, None
        inserted_at, value = row
        age_s = now - inserted_at
        if age_s > ttl:
            del _store[key]
            return None, None
        return value, age_s


def feed_clusters_cache_set(key: str, value: Any) -> None:
    """Store a successful 200 response payload."""
    with _lock:
        _store[key] = (time.time(), value)
