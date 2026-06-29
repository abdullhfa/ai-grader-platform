"""Abuse protection middleware — path-specific Redis rate limits."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.ops.correlation import get_correlation
from app.security.rate_limit import check_rate_limit, limit_for_path


class SecurityAbuseMiddleware(BaseHTTPMiddleware):
    """Rate limit sensitive endpoints: appeals, exports, runtime, governance."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        limit, window = limit_for_path(path)
        sensitive_prefixes = (
            "/api/appeals",
            "/api/governance/export",
            "/api/runtime",
            "/api/governance/override",
            "/api/governance/signoff",
        )
        if not any(path.startswith(p) for p in sensitive_prefixes):
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        key = f"{client}:{path.split('/')[1:4]}"
        allowed, retry = check_rate_limit(key, limit=limit, window_seconds=window)
        if not allowed:
            ctx = get_correlation()
            try:
                from app.security.security_audit import log_security_action

                log_security_action(
                    action="rate_limit_blocked",
                    actor=client,
                    resource=path,
                    outcome="denied",
                    trace_id=ctx.trace_id if ctx else None,
                    ip_address=client,
                )
            except Exception:
                pass
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after_seconds": retry},
            )
        return await call_next(request)
