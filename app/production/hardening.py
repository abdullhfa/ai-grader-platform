"""Production hardening — rate limiting, retries, health checks."""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from typing import Callable, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from app.core.production_config import get_production_config

_HEALTH_PATHS = frozenset({"/health", "/ready", "/api/health", "/api/ready"})

# High-frequency teacher UI polling — must not compete with the global IP bucket.
_RATE_LIMIT_EXEMPT_PREFIXES = (
    "/static/",
    "/api/batch-grade-progress/",
    "/api/batch-meta/",
    "/api/batch-grade-latest/",
    "/api/check-ai-balance",
)


def is_rate_limit_exempt(method: str, path: str) -> bool:
    """Return True when a request should bypass the global per-IP limiter."""
    if path in _HEALTH_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in _RATE_LIMIT_EXEMPT_PREFIXES):
        return True
    # HTML navigation (batch-results, batch-grade, etc.) must stay reachable while grading polls.
    if method == "GET" and not path.startswith("/api/"):
        return True
    return False


def rate_limit_response(request: Request, *, retry_after_seconds: int) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept and not request.url.path.startswith("/api/"):
        html = (
            "<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>"
            "<title>طلبات كثيرة</title></head><body style='font-family:sans-serif;padding:2rem'>"
            "<h1>تم تجاوز حد الطلبات</h1>"
            f"<p>يرجى الانتظار {retry_after_seconds} ثانية ثم تحديث الصفحة.</p>"
            "</body></html>"
        )
        return HTMLResponse(
            content=html,
            status_code=429,
            headers={"Retry-After": str(retry_after_seconds)},
        )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "retry_after_seconds": retry_after_seconds,
        },
        headers={"Retry-After": str(retry_after_seconds)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory sliding-window rate limiter per client IP."""

    def __init__(self, app, *, requests_per_minute: Optional[int] = None):
        super().__init__(app)
        cfg = get_production_config()
        self.rpm = requests_per_minute or cfg.rate_limit_per_minute
        self._hits: Dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if is_rate_limit_exempt(request.method, request.url.path):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self._hits[client]
        window[:] = [t for t in window if now - t < 60.0]
        if len(window) >= self.rpm:
            return rate_limit_response(request, retry_after_seconds=60)
        window.append(now)
        return await call_next(request)


async def retry_async(
    fn: Callable,
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
):
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry_async exhausted with no result")  # pragma: no cover


def build_health_status(db_ok: bool = True) -> Dict[str, object]:
    cfg = get_production_config()
    from app.governance_freeze_registry import get_l4_gate_status

    infra: Dict[str, object] = {}
    try:
        from app.infra.docker_sandbox import docker_sandbox_enabled
        from app.storage.object_store import get_object_store
        from app.tasks.celery_app import is_celery_enabled

        store = get_object_store()
        infra = {
            "celery_enabled": is_celery_enabled(),
            "docker_sandbox": docker_sandbox_enabled(),
            "object_store_backend": store.backend,
            "async_reasoning": os.environ.get("AI_GRADER_ASYNC_REASONING", "0"),
        }
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "environment": cfg.environment,
        "l4_gate": get_l4_gate_status(),
        "infrastructure": infra,
        "features": {
            "l4_sandbox": cfg.enable_l4_sandbox,
            "deterministic_rubric": cfg.enable_deterministic_rubric,
            "ai_reliability": cfg.enable_ai_reliability_layer,
        },
    }
