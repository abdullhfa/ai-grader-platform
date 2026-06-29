"""Production metrics — PHASE E (Prometheus-compatible text export)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, Optional


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)

    def inc(self, name: str, value: float = 1.0, labels: str = "") -> None:
        key = f"{name}{{{labels}}}" if labels else name
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, labels: str = "") -> None:
        key = f"{name}{{{labels}}}" if labels else name
        with self._lock:
            self._gauges[key] = value

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "ts": time.time(),
            }

    def prometheus_text(self) -> str:
        lines = []
        with self._lock:
            for k, v in self._counters.items():
                metric = k.split("{", 1)[0]
                lines.append(f"# TYPE {metric} counter")
                lines.append(f"{k} {v}")
            for k, v in self._gauges.items():
                metric = k.split("{", 1)[0]
                lines.append(f"# TYPE {metric} gauge")
                lines.append(f"{k} {v}")
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


def record_runtime_outcome(status: str) -> None:
    metrics.inc("runtime_observations_total", labels=f'status="{status}"')
    if status in ("completed", "partial"):
        metrics.inc("runtime_success_total")
    elif status in ("error", "timeout"):
        metrics.inc("runtime_crash_total")


def record_replay_verification(verified: bool) -> None:
    metrics.inc("replay_verifications_total")
    if verified:
        metrics.inc("replay_verified_total")
    else:
        metrics.inc("replay_mismatch_total")


def record_calibration_agreement(rate: Optional[float]) -> None:
    if rate is not None:
        metrics.set_gauge("calibration_agreement_rate", float(rate))


def record_grading_latency(seconds: float) -> None:
    metrics.set_gauge("grading_latency_seconds", seconds)


def record_gameplay_analysis(status: str) -> None:
    metrics.inc("gameplay_analysis_total", labels=f'status="{status}"')


def record_reasoning_outcome(status: str, *, manual_review: bool = False) -> None:
    metrics.inc("evidence_reasoning_total", labels=f'status="{status}"')
    if manual_review:
        metrics.inc("evidence_reasoning_manual_review_total")


def record_sandbox_outcome(status: str, isolation: str) -> None:
    metrics.inc("runtime_sandbox_total", labels=f'status="{status}",isolation="{isolation}"')


def record_submission_rejected(reason: str) -> None:
    metrics.inc("submission_guard_rejections_total", labels=f'reason="{reason}"')
