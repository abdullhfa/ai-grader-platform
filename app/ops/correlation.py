"""Distributed tracing correlation IDs — trace/submission/replay/audit."""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

_correlation: ContextVar[Optional["CorrelationContext"]] = ContextVar("correlation", default=None)


@dataclass
class CorrelationContext:
    trace_id: str
    submission_id: Optional[str] = None
    replay_id: Optional[str] = None
    audit_id: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "submission_id": self.submission_id,
            "replay_id": self.replay_id,
            "audit_id": self.audit_id,
            "session_id": self.session_id,
        }


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_correlation(ctx: CorrelationContext) -> None:
    _correlation.set(ctx)


def get_correlation() -> Optional[CorrelationContext]:
    return _correlation.get()


def get_correlation_ids() -> Dict[str, Any]:
    ctx = get_correlation()
    if ctx is None:
        return {"trace_id": None}
    return ctx.to_dict()


def bind_submission(submission_id: str, *, replay_id: Optional[str] = None) -> CorrelationContext:
    ctx = get_correlation() or CorrelationContext(trace_id=new_trace_id())
    ctx.submission_id = submission_id
    if replay_id:
        ctx.replay_id = replay_id
    set_correlation(ctx)
    return ctx
