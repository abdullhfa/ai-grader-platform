"""
Governance Response Protocols v1 + Severity Levels (S1–S5).

Defines institutional responses when GFM failure modes trigger.
Observation → structured response → self-correction (not auto-grade mutation).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.governance_failure_taxonomy import FAILURE_MODES, TAXONOMY_ID

PROTOCOL_ID = "GOVERNANCE_RESPONSE_PROTOCOLS_v1"

# Unified severity ladder (institutional risk calibration)
SEVERITY_LEVELS: Dict[str, Dict[str, Any]] = {
    "S1": {
        "label_en": "wording_drift",
        "label_ar": "انحراف صياغة",
        "risk": "low",
        "human_required": False,
    },
    "S2": {
        "label_en": "replay_omission",
        "label_ar": "نقص provenance",
        "risk": "low_medium",
        "human_required": False,
    },
    "S3": {
        "label_en": "hidden_contradiction",
        "label_ar": "تعارض مخفي",
        "risk": "medium",
        "human_required": True,
    },
    "S4": {
        "label_en": "authority_escalation",
        "label_ar": "تصعيد سلطة",
        "risk": "high",
        "human_required": True,
    },
    "S5": {
        "label_en": "silent_false_verification",
        "label_ar": "تحقق زائف صامت",
        "risk": "critical",
        "human_required": True,
    },
}

# GFM → default severity
_GFM_SEVERITY: Dict[str, str] = {
    "GFM_SEMANTIC_ESCALATION": "S1",
    "GFM_REPLAY_INCOMPLETENESS": "S2",
    "GFM_BOUNDARY_OMISSION": "S2",
    "GFM_FALSE_CORROBORATION": "S3",
    "GFM_CONTRADICTION_INVISIBILITY": "S3",
    "GFM_MODALITY_DOMINANCE": "S3",
    "GFM_AUTHORITY_INFLATION": "S4",
    "GFM_DRIFT_SILENCE": "S5",
    "GFM_REVIEWER_AUTHORITY_CONFUSION": "S4",
    "GFM_TRUST_EROSION": "S5",
}

# Drift monitor severity → bump
_DRIFT_SEVERITY_BUMP = {
    "low": 0,
    "medium": 0,
    "high": 1,
    "critical": 2,
}


def _bump_severity(base: str, bump: int) -> str:
    order = ["S1", "S2", "S3", "S4", "S5"]
    try:
        idx = order.index(base)
    except ValueError:
        idx = 0
    return order[min(len(order) - 1, idx + bump)]


# GFM → institutional response protocol
RESPONSE_PROTOCOLS: Dict[str, Dict[str, Any]] = {
    "GFM_AUTHORITY_INFLATION": {
        "actions": [
            "freeze_escalation",
            "wording_review_required",
            "sanitize_claim_language",
        ],
        "actions_ar": [
            "تجميد أي authority escalation",
            "مراجعة صياغة التقرير",
            "استبدال لغة verification المحظورة",
        ],
        "export_gate": "advisory_warning",
        "replay_required": True,
    },
    "GFM_MODALITY_DOMINANCE": {
        "actions": [
            "downgrade_visual_hints",
            "surface_cross_artifact_ambiguity",
            "block_video_authority_language",
        ],
        "actions_ar": [
            "خفض سلطة hints البصرية/الزمنية",
            "إظهار cross-artifact ambiguity",
            "منع لغة video-as-verification",
        ],
        "export_gate": "advisory_warning",
        "replay_required": True,
    },
    "GFM_REPLAY_INCOMPLETENESS": {
        "actions": [
            "flag_report_export",
            "rebuild_authority_replay",
            "log_provenance_gap",
        ],
        "actions_ar": [
            "تحذير على تصدير التقرير — provenance ناقص",
            "إعادة بناء authority replay",
            "تسجيل فجوة provenance",
        ],
        "export_gate": "conditional_block",
        "replay_required": True,
    },
    "GFM_DRIFT_SILENCE": {
        "actions": [
            "governance_alert",
            "halt_capability_expansion",
            "mandatory_freeze_audit",
        ],
        "actions_ar": [
            "تنبيه governance — freeze violation",
            "إيقاف أي توسعة capability",
            "تدقيق freeze إلزامي",
        ],
        "export_gate": "block_until_review",
        "replay_required": True,
    },
    "GFM_CONTRADICTION_INVISIBILITY": {
        "actions": [
            "surface_contradiction_in_replay",
            "inject_claim_authority_flags",
            "downgrade_temporal_authority",
        ],
        "actions_ar": [
            "إظهار contradiction في replay",
            "تفعيل claim_authority_flags",
            "خفض temporal authority",
        ],
        "export_gate": "advisory_warning",
        "replay_required": True,
    },
    "GFM_SEMANTIC_ESCALATION": {
        "actions": [
            "sanitize_claim_language",
            "log_overclaim_flag",
        ],
        "actions_ar": [
            "sanitize صياغة claims",
            "تسجيل overclaim flag",
        ],
        "export_gate": "none",
        "replay_required": False,
    },
    "GFM_FALSE_CORROBORATION": {
        "actions": [
            "mark_hint_authority_weak",
            "require_corroboration_note",
        ],
        "actions_ar": [
            "توسيم hint authority كضعيف",
            "طلب corroboration صريح",
        ],
        "export_gate": "advisory_warning",
        "replay_required": False,
    },
    "GFM_BOUNDARY_OMISSION": {
        "actions": [
            "inject_coverage_notice",
            "flag_report_export",
        ],
        "actions_ar": [
            "إضافة grading_coverage_notice",
            "تحذير export — حدود السلطة غائبة",
        ],
        "export_gate": "conditional_block",
        "replay_required": False,
    },
    "GFM_REVIEWER_AUTHORITY_CONFUSION": {
        "actions": [
            "mandatory_human_moderation",
            "replay_consultation_required",
            "hold_until_clarified",
        ],
        "actions_ar": [
            "moderation بشرية إلزامية",
            "استشارة authority replay",
            "HOLD حتى توضيح السلطة",
        ],
        "export_gate": "block_until_review",
        "replay_required": True,
    },
    "GFM_TRUST_EROSION": {
        "actions": [
            "mandatory_human_moderation",
            "workshop_incident_log",
            "freeze_autonomous_claims",
        ],
        "actions_ar": [
            "moderation بشرية إلزامية",
            "تسجيل workshop incident",
            "تجميد claims آلية مستقلة",
        ],
        "export_gate": "block_until_review",
        "replay_required": True,
    },
}


def resolve_severity(
    failure_mode_id: str,
    *,
    drift_severity: Optional[str] = None,
) -> Dict[str, Any]:
    """Map GFM + drift signal severity to unified S1–S5."""
    base = _GFM_SEVERITY.get(failure_mode_id, "S2")
    bump = _DRIFT_SEVERITY_BUMP.get(str(drift_severity or "low").lower(), 0)
    level = _bump_severity(base, bump)
    meta = SEVERITY_LEVELS.get(level, {})
    return {
        "severity_level": level,
        "severity_label_en": meta.get("label_en"),
        "severity_label_ar": meta.get("label_ar"),
        "risk": meta.get("risk"),
        "human_review_required": meta.get("human_required", False),
    }


def resolve_response_protocol(failure_mode_id: str) -> Dict[str, Any]:
    """Institutional response when GFM triggers."""
    proto = RESPONSE_PROTOCOLS.get(failure_mode_id, {})
    return {
        "protocol_id": PROTOCOL_ID,
        "failure_mode_id": failure_mode_id,
        "actions": proto.get("actions") or ["log_governance_signal"],
        "actions_ar": proto.get("actions_ar") or ["تسجيل إشارة governance"],
        "export_gate": proto.get("export_gate") or "none",
        "replay_required": proto.get("replay_required", False),
    }


def build_governance_responses(
    classified_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build response plan from classified drift/taxonomy signals.
    Does not mutate grades — returns institutional self-correction plan.
    """
    responses: List[Dict[str, Any]] = []
    max_severity = "S1"
    order = ["S1", "S2", "S3", "S4", "S5"]
    export_gates: List[str] = []
    human_required = False
    replay_required = False

    for sig in classified_signals:
        gfm = str(sig.get("failure_mode_id") or "")
        if not gfm:
            continue
        sev = resolve_severity(gfm, drift_severity=sig.get("severity"))
        proto = resolve_response_protocol(gfm)
        if order.index(sev["severity_level"]) > order.index(max_severity):
            max_severity = sev["severity_level"]
        if sev.get("human_review_required"):
            human_required = True
        if proto.get("replay_required"):
            replay_required = True
        gate = proto.get("export_gate") or "none"
        if gate != "none":
            export_gates.append(gate)

        responses.append({
            **sig,
            **sev,
            **proto,
            "response_summary_ar": (
                f"{gfm} → {sev['severity_level']}: "
                + "; ".join(proto.get("actions_ar") or [])
            ),
        })

    export_policy = _aggregate_export_gate(export_gates, max_severity)

    return {
        "version": 1,
        "protocol_id": PROTOCOL_ID,
        "taxonomy_id": TAXONOMY_ID,
        "response_count": len(responses),
        "max_severity": max_severity,
        "human_review_required": human_required,
        "replay_consultation_required": replay_required,
        "export_policy": export_policy,
        "responses": responses,
        "summary_ar": _build_summary_ar(max_severity, export_policy, human_required),
    }


def _aggregate_export_gate(gates: List[str], max_severity: str) -> Dict[str, Any]:
    """Derive export policy from worst gate + severity."""
    priority = {
        "none": 0,
        "advisory_warning": 1,
        "conditional_block": 2,
        "block_until_review": 3,
    }
    worst_gate = "none"
    for g in gates:
        if priority.get(g, 0) > priority.get(worst_gate, 0):
            worst_gate = g
    if max_severity in ("S4", "S5") and priority.get(worst_gate, 0) < 2:
        worst_gate = "conditional_block"
    if max_severity == "S5":
        worst_gate = "block_until_review"

    allow_export = worst_gate in ("none", "advisory_warning")
    return {
        "gate": worst_gate,
        "allow_export": allow_export,
        "message_ar": {
            "none": "التصدير مسموح — لا governance block.",
            "advisory_warning": "التصدير مسموح مع تحذير governance.",
            "conditional_block": "التصدير يتطلب مراجعة — provenance/authority gap.",
            "block_until_review": "التصدير موقوف حتى moderation بشرية.",
        }.get(worst_gate, ""),
    }


def _build_summary_ar(max_sev: str, export: Dict[str, Any], human: bool) -> str:
    parts = [f"أقصى خطورة: {max_sev}."]
    parts.append(export.get("message_ar") or "")
    if human:
        parts.append("مراجعة بشرية مطلوبة.")
    return " ".join(p for p in parts if p)


def enrich_drift_with_responses(drift_report: Dict[str, Any]) -> Dict[str, Any]:
    """Attach governance response protocols to drift report."""
    signals = drift_report.get("drift_signals") or []
    responses = build_governance_responses(signals)
    return {
        **drift_report,
        "governance_responses": responses,
    }
