"""
Execution phenomenology — describe what appeared during execution, not what it means.

Canonical descriptors: PHENOMENOLOGY_MANIFEST_v1.json (execution domain)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.phenomenology_manifest import (
    MANIFEST_ID,
    descriptors as _descriptors,
    domain_invariant,
    escalation_pairs as _escalation_pairs,
    forbidden_escalations as _forbidden_escalations,
)

SCHEMA_ID = MANIFEST_ID
SPEC_ID = "PROVENANCE_AWARE_EXECUTION_SANDBOX_SPEC_v1"

PRIMARY_INVARIANT_EN = domain_invariant("execution")
PRIMARY_INVARIANT_AR = "التنفيذ المرئي لا يعادل التنفيذ المُ validated."

PHENOMENOLOGY_DESCRIPTORS = _descriptors("execution")
FORBIDDEN_ESCALATIONS = _forbidden_escalations("execution")
ESCALATION_PAIRS: List[Tuple[str, str]] = _escalation_pairs("execution")

FORBIDDEN_ESCALATION_PATTERNS: List[Tuple[str, str]] = [
    (r"\bgame\s+works\b", "process launched — observation only"),
    (r"\bgameplay\s+verified\b", "frames rendered — observation only"),
    (r"\bmechanics\s+validated\b", "input responded — observation only"),
    (r"\brubric\s+achieved\b", "executable persisted — observation only"),
    (r"\bgame\s+confirmed\b", "window detected — observation only"),
    (r"\bruntime\s+truth\b", "telemetry stream active — observation only"),
    (r"\bprovenance\s+validated\b", "replay captured — observation only"),
    (r"\bsuccess\s+inferred\b", "phenomenology only — no legitimacy"),
    (r"اللعبة\s+تعمل", "process launched — observation only"),
    (r"تم\s+التحقق\s+من\s+اللعب", "frames rendered — observation only"),
]


def build_phenomenology_record(
    descriptors: List[str],
    *,
    t_offset_ms: int = 0,
    detail: Dict[str, Any] | None = None,
    source: str = "sandbox",
) -> Dict[str, Any]:
    """Structured phenomenology — no meaning escalation."""
    unknown = [d for d in descriptors if d not in PHENOMENOLOGY_DESCRIPTORS]
    if unknown:
        raise ValueError(f"unknown phenomenology descriptor(s): {', '.join(unknown)}")
    return {
        "manifest_id": SCHEMA_ID,
        "domain": "execution",
        "spec_id": SPEC_ID,
        "layer": "execution_phenomenology",
        "descriptors": list(descriptors),
        "t_offset_ms": t_offset_ms,
        "source": source,
        "detail": detail or {},
        "invariant_en": PRIMARY_INVARIANT_EN,
    }


def validate_phenomenology_text(text: str) -> Dict[str, Any]:
    """Reject text that escalates phenomenology to legitimacy."""
    violations: List[Dict[str, str]] = []
    lower = (text or "").lower()
    for forbidden in FORBIDDEN_ESCALATIONS:
        if forbidden.replace("_", " ") in lower or forbidden in lower:
            violations.append({"type": "forbidden_escalation", "phrase": forbidden})
    for pattern, suggested in FORBIDDEN_ESCALATION_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            violations.append({"type": "pattern", "pattern": pattern, "suggested": suggested})
    return {
        "manifest_id": SCHEMA_ID,
        "domain": "execution",
        "allowed": len(violations) == 0,
        "violations": violations,
        "invariant_en": PRIMARY_INVARIANT_EN,
    }


def describe_phenomenology_en(descriptors: List[str]) -> str:
    """Human-readable phenomenology-only summary — no escalation."""
    labels = {
        "process_launched": "A process launch was observed.",
        "window_detected": "A window surface was detected.",
        "frames_rendered": "Frame output was observed.",
        "input_responded": "Input events received a response signal.",
        "telemetry_stream_active": "A telemetry stream was active.",
        "execution_continuity_observed": "Execution continuity was observed within the window.",
        "executable_persisted": "The executable artifact persisted on disk.",
        "replay_captured": "A replay capture was recorded.",
        "crash_observed": "A crash signal was observed.",
        "timeout_reached": "The observation window timeout was reached.",
    }
    parts = [labels.get(d, d) for d in descriptors if d in PHENOMENOLOGY_DESCRIPTORS]
    summary = " ".join(parts) if parts else "No phenomenology descriptors recorded."
    check = validate_phenomenology_text(summary)
    if not check["allowed"]:
        raise ValueError("generated phenomenology summary failed escalation check")
    return summary + " Human review required for any trust or legitimacy claim."
