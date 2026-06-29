"""Operational dashboard metrics — governance health, queue, integrity."""
from __future__ import annotations

from typing import Any, Dict

from app.observability.metrics import metrics


def operational_dashboard_snapshot() -> Dict[str, Any]:
    snap = metrics.snapshot()
    counters = snap.get("counters") or {}
    gauges = snap.get("gauges") or {}

    def _get(prefix: str) -> float:
        total = 0.0
        for k, v in counters.items():
            if k.startswith(prefix):
                total += float(v)
        return total

    runtime_failures = _get("runtime_crash_total")
    hallucination_rejects = _get("evidence_reasoning_manual_review_total")
    appeal_submissions = _get("appeal_")  # may be 0 until instrumented
    replay_mismatch = _get("replay_mismatch_total")
    guard_rejections = _get("submission_guard_rejections_total")

    return {
        "schema": "operational_dashboard_v1",
        "metrics": {
            "runtime_failures": runtime_failures,
            "hallucination_manual_review": hallucination_rejects,
            "appeal_submissions": appeal_submissions,
            "replay_mismatch": replay_mismatch,
            "suspicious_submissions": guard_rejections,
            "grading_latency_seconds": gauges.get("grading_latency_seconds"),
            "calibration_agreement_rate": gauges.get("calibration_agreement_rate"),
        },
        "raw_counters": counters,
        "raw_gauges": gauges,
        "health_indicators": {
            "governance": "healthy" if replay_mismatch == 0 else "investigate",
            "integrity": "healthy" if guard_rejections < 10 else "elevated",
            "ai_quality": "healthy" if hallucination_rejects < 50 else "review",
        },
    }
