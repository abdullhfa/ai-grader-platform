"""Confidence tier system — A/B/C/D for institutional assessment."""
from __future__ import annotations

from typing import Any, Dict, Optional


TIER_LABELS = {
    "A": "runtime_verified",
    "B": "export_verified",
    "C": "static_inference",
    "D": "examiner_heavy",
}

TIER_DESCRIPTIONS_AR = {
    "A": "تم التحقق عبر runtime — play session / smoke test",
    "B": "تم التحقق عبر export أو build artifact",
    "C": "استدلال static — source/artifact analysis بدون runtime كامل",
    "D": "يتطلب مراجعة examiner معززة — build/docs/engine gaps",
}


def compute_confidence_tier(
    *,
    engine_id: Optional[str],
    status: str,
    runtime_method: Optional[str],
    validity: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Map session outcome to institutional confidence tier A–D."""
    validity = validity or {}
    metrics = metrics or {}
    method = (runtime_method or "").lower()
    warnings = set(validity.get("warnings") or [])
    issues = set(validity.get("issues") or [])

    if issues & {"corrupted_zip"}:
        tier = "D"
        score = 0.15
    elif status in ("failed", "crashed", "timeout") and not method:
        tier = "D"
        score = 0.20
    elif status in ("failed", "crashed", "timeout") and method:
        # Smoke/watchdog ended early — partial observation, not empty submission
        if method in (
            "legacy_smoke_test",
            "godot_pck_smoke",
            "godot_main_pack_smoke",
            "godot_exe_smoke",
            "controlled_static_and_smoke",
        ):
            tier = "B"
            score = 0.68
        elif method in ("godot_static_analysis", "unity_static_only", "static_only"):
            tier = "C"
            score = 0.48
        else:
            tier = "C"
            score = 0.42
    elif not engine_id or "unsupported_or_unknown_engine" in warnings:
        tier = "D"
        score = 0.25
    elif method in (
        "unity_play_session_v2",
        "unity_play_session",
        "godot_exe_smoke",
        "godot_pck_smoke",
        "godot_main_pack_smoke",
        "gamemaker_exe_smoke",
        "web_headless",
        "legacy_smoke_test",
        "controlled_static_and_smoke",
        "static_only",
    ) and status in ("completed", "partial", "failed"):
        if metrics.get("crash_detected"):
            tier = "C"
            score = 0.45
        elif method in (
            "unity_play_session_v2",
            "unity_play_session",
            "godot_exe_smoke",
            "godot_main_pack_smoke",
            "gamemaker_exe_smoke",
        ):
            tier = "A"
            score = 0.88
        elif method in ("legacy_smoke_test", "godot_pck_smoke", "controlled_static_and_smoke"):
            tier = "B"
            score = 0.74
        elif method == "web_headless" or method == "static_only":
            tier = "B" if method == "web_headless" else "C"
            score = 0.75 if tier == "B" else 0.55
        else:
            tier = "A"
            score = 0.85
    elif method in ("godot_headless_export",) or "export" in method:
        tier = "B"
        score = 0.72
    elif method in (
        "godot_static_analysis",
        "gamemaker_artifact_analysis",
        "unity_static_only",
        "godot_static_only",
    ):
        tier = "C"
        score = 0.50
    elif status == "skipped":
        tier = "D"
        score = 0.30
    else:
        tier = "C"
        score = 0.48

    if "missing_build" in warnings and tier == "A":
        tier = "C"
        score = min(score, 0.52)
    if "missing_documentation" in warnings:
        score = max(0.0, score - 0.05)
    if "missing_source" in warnings and tier == "A":
        score = max(0.0, score - 0.08)

    examiner_required = tier in ("C", "D") or bool(warnings) or bool(issues)

    return {
        "schema": "confidence_tier_v1",
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "confidence_score": round(score, 3),
        "confidence_pct": round(score * 100),
        "examiner_signoff_required": examiner_required,
        "description_ar": TIER_DESCRIPTIONS_AR[tier],
        "human_signoff_mandatory": True,
    }
