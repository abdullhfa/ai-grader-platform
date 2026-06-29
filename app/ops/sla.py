"""Operational SLAs — institutional service level targets."""
from __future__ import annotations

import os
from typing import Any, Dict

DEFAULT_SLAS: Dict[str, Dict[str, Any]] = {
    "runtime_evaluation": {
        "target_seconds": int(os.environ.get("AI_GRADER_SLA_RUNTIME_SEC", "300")),
        "description": "Full runtime observation + smoke",
    },
    "gameplay_analysis": {
        "target_seconds": int(os.environ.get("AI_GRADER_SLA_GAMEPLAY_SEC", "180")),
        "description": "CV + timeline pipeline",
    },
    "evidence_reasoning": {
        "target_seconds": int(os.environ.get("AI_GRADER_SLA_REASONING_SEC", "120")),
        "description": "Multi-agent evidence arbitration",
    },
    "replay_restore": {
        "target_seconds": int(os.environ.get("AI_GRADER_SLA_REPLAY_RESTORE_SEC", "5")),
        "description": "Replay bundle load from archive",
    },
    "appeal_review": {
        "target_hours": int(os.environ.get("AI_GRADER_SLA_APPEAL_HOURS", "72")),
        "description": "Independent examiner appeal review",
    },
    "malware_scan": {
        "target_seconds": int(os.environ.get("AI_GRADER_SLA_MALWARE_SCAN_SEC", "60")),
        "description": "Quarantine + scan pipeline",
    },
}


def get_sla_definitions() -> Dict[str, Any]:
    return {
        "schema": "operational_sla_v1",
        "environment": os.environ.get("AI_GRADER_ENV", "production"),
        "slas": DEFAULT_SLAS,
    }


def check_latency_against_sla(operation: str, elapsed_seconds: float) -> Dict[str, Any]:
    sla = DEFAULT_SLAS.get(operation)
    if not sla:
        return {"operation": operation, "status": "unknown_operation"}
    target = sla.get("target_seconds") or (sla.get("target_hours", 0) * 3600)
    breached = elapsed_seconds > target
    return {
        "operation": operation,
        "elapsed_seconds": elapsed_seconds,
        "target_seconds": target,
        "breached": breached,
        "status": "breach" if breached else "ok",
    }
