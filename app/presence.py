"""Client poll presence tracking for admin online indicator."""

from __future__ import annotations

import threading
import time
from typing import Dict

from app import config

_lock = threading.Lock()
_presence: Dict[str, float] = {}


def touch(session_id: str) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    now = time.time()
    with _lock:
        _presence[sid] = now
        cutoff = now - config.CHAT_PRESENCE_TTL_SECONDS
        stale = [k for k, ts in _presence.items() if ts < cutoff]
        for k in stale:
            del _presence[k]


def snapshot() -> Dict[str, float]:
    now = time.time()
    cutoff = now - config.CHAT_PRESENCE_TTL_SECONDS
    with _lock:
        return {k: v for k, v in _presence.items() if v >= cutoff}
