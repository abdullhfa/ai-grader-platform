"""Correlation ID middleware — propagates trace_id on every request."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.ops.correlation import CorrelationContext, new_trace_id, set_correlation


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = (
            request.headers.get("X-Trace-Id")
            or request.headers.get("X-Request-Id")
            or new_trace_id()
        )
        ctx = CorrelationContext(
            trace_id=trace_id,
            submission_id=request.headers.get("X-Submission-Id"),
            replay_id=request.headers.get("X-Replay-Id"),
            audit_id=request.headers.get("X-Audit-Id"),
            session_id=request.headers.get("X-Session-Id"),
        )
        set_correlation(ctx)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        if ctx.submission_id:
            response.headers["X-Submission-Id"] = ctx.submission_id
        return response
