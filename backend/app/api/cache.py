"""Tiny in-process TTL cache for slow overview endpoints (worklist, hospitals).

Request actions call `invalidate()` so the coordinator always sees the effect of a click.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

TTL_SECONDS = 25.0

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def cached(key: str, compute: Callable[[], Any], ttl: float = TTL_SECONDS,
           keep: Callable[[Any], bool] = lambda _: True) -> Any:
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
    value = compute()
    if keep(value):
        with _lock:
            _store[key] = (time.monotonic(), value)
    return value


def invalidate() -> None:
    with _lock:
        _store.clear()
