"""In-memory login brute-force lockout (per email + IP)."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict, Tuple

_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

_failures: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))


def _key(email: str, ip: str) -> str:
    return f"{email.strip().lower()}|{ip or 'unknown'}"


def is_locked(email: str, ip: str) -> Tuple[bool, int]:
    """Return (locked, seconds_remaining)."""
    count, locked_until = _failures[_key(email, ip)]
    if locked_until <= time.time():
        if count >= _MAX_ATTEMPTS:
            _failures[_key(email, ip)] = (0, 0.0)
        return False, 0
    return True, max(0, int(locked_until - time.time()))


def record_failure(email: str, ip: str) -> None:
    k = _key(email, ip)
    count, locked_until = _failures[k]
    if locked_until > time.time():
        return
    count += 1
    if count >= _MAX_ATTEMPTS:
        _failures[k] = (count, time.time() + _LOCKOUT_SECONDS)
    else:
        _failures[k] = (count, 0.0)


def record_success(email: str, ip: str) -> None:
    _failures.pop(_key(email, ip), None)
