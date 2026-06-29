"""Redis-backed rate limiting with in-memory fallback."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

_PATH_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/appeals": (20, 60),
    "/api/governance/export": (30, 60),
    "/api/runtime": (40, 60),
    "/api/governance/override": (15, 60),
    "/api/governance/signoff": (10, 60),
}


def _redis_client():
    url = os.environ.get("AI_GRADER_REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None


_memory: Dict[str, list[float]] = defaultdict(list)


def check_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int = 60,
) -> Tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    client = _redis_client()
    if client is not None:
        try:
            rkey = f"rl:{key}:{window_seconds}"
            count = client.incr(rkey)
            if count == 1:
                client.expire(rkey, window_seconds)
            if count > limit:
                ttl = client.ttl(rkey)
                return False, max(int(ttl), 1)
            return True, 0
        except Exception:
            pass

    now = time.monotonic()
    bucket = _memory[key]
    bucket[:] = [t for t in bucket if now - t < window_seconds]
    if len(bucket) >= limit:
        return False, window_seconds
    bucket.append(now)
    return True, 0


def limit_for_path(path: str) -> Tuple[int, int]:
    for prefix, cfg in _PATH_LIMITS.items():
        if path.startswith(prefix):
            return cfg
    rpm = int(os.environ.get("AI_GRADER_RATE_LIMIT", "120"))
    return rpm, 60
