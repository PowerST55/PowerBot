from __future__ import annotations

import os
import threading
import time
from typing import Optional

_lock = threading.Lock()
_exhausted_until_ts: float = 0.0
_last_reason: str = ""
_DEFAULT_BLOCK_SECONDS = int(os.getenv("YT_QUOTA_BLOCK_SECONDS", "3600"))


def mark_quota_exhausted(reason: str = "quotaExceeded", block_seconds: Optional[int] = None) -> int:
    """Marks YouTube quota as exhausted for a configurable cooldown window."""
    global _exhausted_until_ts, _last_reason
    seconds = int(block_seconds or _DEFAULT_BLOCK_SECONDS)
    until_ts = time.time() + max(1, seconds)
    with _lock:
        _exhausted_until_ts = max(_exhausted_until_ts, until_ts)
        _last_reason = str(reason or "quotaExceeded")
    return seconds


def clear_quota_exhausted() -> None:
    """Clears quota exhaustion state manually (e.g., after daily reset)."""
    global _exhausted_until_ts, _last_reason
    with _lock:
        _exhausted_until_ts = 0.0
        _last_reason = ""


def is_quota_exhausted() -> bool:
    with _lock:
        return time.time() < _exhausted_until_ts


def get_remaining_seconds() -> int:
    with _lock:
        remaining = int(_exhausted_until_ts - time.time())
    return max(0, remaining)


def get_quota_status() -> dict:
    with _lock:
        exhausted = time.time() < _exhausted_until_ts
        remaining = int(_exhausted_until_ts - time.time())
        reason = _last_reason
    return {
        "exhausted": exhausted,
        "remaining_seconds": max(0, remaining),
        "reason": reason,
    }
