"""Failsafe pipeline — NEVER return empty assessment results."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.submission.confidence_tiers import compute_confidence_tier
from app.submission.normalize import normalize_submission
from app.submission.validity_policy import assess_submission_validity
from app.runtime_engines.normalization import normalize_runtime_manifest


FAILSAFE_SCHEMA = "failsafe_assessment_v1"


def wrap_failsafe_session_result(
    result: Dict[str, Any],
    *,
    root: Optional[Path] = None,
    paths: Optional[Sequence[str]] = None,
    submission_key: str = "",
) -> Dict[str, Any]:
    """Ensure every runtime session returns a complete assessment envelope."""
    if not isinstance(result, dict):
        result = {"status": "failed", "errors": ["invalid_session_result"]}

    validity = assess_submission_validity(root, paths=paths) if root else result.get("submission_validity")
    if root and not result.get("submission_validity"):
        result["submission_validity"] = validity

    if root and not result.get("submission_normalization"):
        result["submission_normalization"] = normalize_submission(
            root, paths=paths, submission_key=submission_key
        )

    engine = result.get("engine") or validity.get("engine_id") if validity else None
    signals = result.get("signals") or {}
    runtime_method = signals.get("runtime_method")
    status = str(result.get("status") or "unknown")

    tier = compute_confidence_tier(
        engine_id=engine,
        status=status,
        runtime_method=runtime_method,
        validity=validity,
        metrics=result.get("metrics"),
    )
    try:
        from app.runtime_evidence_promotion import (
            apply_confidence_tier_floor,
            assess_runtime_evidence_promotion,
        )

        signals = result.get("signals") or {}
        nested_obs = signals.get("godot_observation") or signals.get("legacy_observation") or {}
        promotion = assess_runtime_evidence_promotion(
            {
                **result,
                "runtime_screenshots": result.get("runtime_screenshots")
                or nested_obs.get("runtime_screenshots"),
                "legacy_observation": nested_obs,
                "platform_analyses": result.get("platform_analyses"),
            }
        )
        tier = apply_confidence_tier_floor(tier, promotion)
        result["runtime_evidence_promotion"] = promotion
        if promotion.get("partial_runtime_verified"):
            result["partial_runtime_verified"] = True
            signals["runtime_evidence_promotion"] = promotion
            result["signals"] = signals
    except Exception:
        pass
    result["confidence_tier"] = tier

    if not result.get("normalized"):
        result["normalized"] = _minimal_normalized(result, engine, submission_key, tier)

    if status in ("failed", "skipped", "gated") and not signals.get("runtime_method"):
        result = _apply_static_fallback(result, root, engine, validity)

    result["failsafe"] = {
        "schema": FAILSAFE_SCHEMA,
        "pipeline_completed": True,
        "never_empty": True,
        "grading_summary": _grading_summary(result, tier, validity),
        "reviewer_notes_section": _reviewer_notes(result, tier, validity),
        "audit_trail_hint": "replay_snapshot + confidence_tier + submission_validity",
    }

    if result.get("status") in ("failed", "skipped") and tier["tier"] in ("C", "D"):
        result["status"] = "partial"

    result["normalized"] = normalize_runtime_manifest(result)
    return result


def wrap_failsafe_observation(observation: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    """Failsafe wrapper for run_runtime_observation output."""
    if not observation.get("platform_analyses") and observation.get("status") != "gated":
        observation["platform_analyses"] = [
            {
                "platform": observation.get("engine") or "unknown",
                "status": observation.get("status"),
                "signals": {},
            }
        ]
    if not observation.get("failsafe"):
        observation["failsafe"] = {
            "schema": FAILSAFE_SCHEMA,
            "pipeline_completed": True,
            "never_empty": True,
        }
    return observation


def _apply_static_fallback(
    result: Dict[str, Any],
    root: Optional[Path],
    engine: Optional[str],
    validity: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attempt static analysis when runtime path failed."""
    if not root or not engine:
        return result

    signals = dict(result.get("signals") or {})
    try:
        if engine == "godot":
            from app.runtime_engines.godot.export_runner import analyze_godot_project

            static = analyze_godot_project(root)
            signals["godot_project_analysis"] = static
            signals["runtime_method"] = "godot_static_analysis"
        elif engine == "gamemaker":
            from app.runtime_engines.gamemaker.build_runner import analyze_gamemaker_artifacts
            from app.runtime_engines.gamemaker.project_probe import probe_gamemaker_layout

            layout = probe_gamemaker_layout(root)
            signals["artifact_analysis"] = analyze_gamemaker_artifacts(layout)
            signals["runtime_method"] = "gamemaker_artifact_analysis"
        elif engine == "unity":
            from app.runtime_engines.unity.scene_validator import validate_unity_scenes

            signals["scene_validation"] = validate_unity_scenes(root)
            signals["runtime_method"] = "unity_static_only"
    except Exception as exc:
        result.setdefault("errors", []).append(f"static_fallback_error:{exc}")
        return result

    result["signals"] = signals
    result["static_fallback_applied"] = True
    if result.get("status") == "failed":
        result["status"] = "partial"
    return result


def _minimal_normalized(
    result: Dict[str, Any],
    engine: Optional[str],
    submission_key: str,
    tier: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "runtime_observation": {
            "schema": "runtime_observation_v1",
            "session_id": result.get("session_id"),
            "engine_id": engine,
            "submission_key": submission_key,
            "status": result.get("status"),
            "confidence_tier": tier.get("tier"),
        },
        "gameplay_timeline": {"duration_seconds": 0.0, "event_count": 0, "events": []},
        "evidence_bundle": {
            "schema": "evidence_bundle_v1",
            "engine_id": engine,
            "confidence_tier": tier,
        },
    }


def _grading_summary(
    result: Dict[str, Any],
    tier: Dict[str, Any],
    validity: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    validity = validity or {}
    return {
        "engine": result.get("engine") or validity.get("engine_id"),
        "status": result.get("status"),
        "confidence_tier": tier.get("tier"),
        "confidence_pct": tier.get("confidence_pct"),
        "examiner_signoff_required": tier.get("examiner_signoff_required"),
        "validity": validity.get("validity"),
        "warnings": validity.get("warnings") or [],
        "static_fallback": bool(result.get("static_fallback_applied")),
        "message_ar": (
            "تم إنتاج تقرير assessment — evidence-based with mandatory human signoff."
        ),
    }


def _reviewer_notes(
    result: Dict[str, Any],
    tier: Dict[str, Any],
    validity: Optional[Dict[str, Any]],
) -> List[str]:
    notes: List[str] = []
    validity = validity or {}
    for w in validity.get("warnings") or []:
        notes.append(f"validity_warning:{w}")
    for issue in validity.get("issues") or []:
        notes.append(f"validity_issue:{issue}")
    if tier.get("examiner_signoff_required"):
        notes.append("examiner_signoff_required:true")
    for err in result.get("errors") or []:
        notes.append(f"runtime_error:{err}")
    if not notes:
        notes.append("no_blockers_detected")
    return notes
