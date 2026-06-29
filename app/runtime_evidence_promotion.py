"""Runtime evidence promotion — tier/classification from smoke + screenshots (no new AI)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _collect_screenshots(observation: Dict[str, Any], inventory: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    shots: List[Dict[str, Any]] = []
    inv = inventory or {}

    for src in (
        observation.get("runtime_screenshots"),
        (observation.get("platform_analyses") or [{}])[0]
        .get("signals", {})
        .get("legacy_observation", {})
        .get("runtime_screenshots"),
        observation.get("legacy_observation", {}).get("runtime_screenshots")
        if isinstance(observation.get("legacy_observation"), dict)
        else None,
        (inv.get("executable_artifacts") or {}).get("runtime_screenshots"),
    ):
        if isinstance(src, list):
            for item in src:
                if isinstance(item, dict) and item not in shots:
                    shots.append(item)
    return shots


def _smoke_stable(observation: Dict[str, Any], inventory: Optional[Dict[str, Any]] = None) -> bool:
    inv = inventory or {}
    legacy = (observation.get("platform_analyses") or [{}])[0]
    legacy_obs = legacy.get("signals", {}).get("legacy_observation") or {}
    if not isinstance(legacy_obs, dict):
        legacy_obs = {}
    for block in (
        legacy_obs,
        observation.get("legacy_observation") if isinstance(observation.get("legacy_observation"), dict) else {},
        observation,
    ):
        if block.get("smoke_result") in ("stable_window", "launch_ok"):
            return True
        analyses = block.get("artifact_analyses") or []
        if any(
            isinstance(a, dict) and a.get("smoke_result") in ("stable_window", "launch_ok")
            for a in analyses
        ):
            return True
    exe = inv.get("executable_artifacts") or {}
    return exe.get("runtime_observation") == "completed" and bool(
        exe.get("runtime_observed")
    )


def assess_runtime_evidence_promotion(
    observation: Optional[Dict[str, Any]] = None,
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Promote confidence when stable smoke + visual gameplay hints exist."""
    obs = observation or {}
    inv = inventory or {}
    shots = _collect_screenshots(obs, inv)
    captured = [s for s in shots if s.get("status") == "captured"]
    gameplay_hits = sum(
        1 for s in captured if s.get("visual_state") == "gameplay_candidate"
    )
    stable = _smoke_stable(obs, inv)
    runtime_observed = bool(
        obs.get("runtime_observed")
        or (inv.get("executable_artifacts") or {}).get("runtime_observed")
    )

    partial_verified = stable and len(captured) >= 2
    strong_partial = partial_verified and gameplay_hits >= 1

    min_tier = None
    if strong_partial:
        min_tier = "B"
    elif partial_verified:
        min_tier = "B"
    elif stable and runtime_observed:
        min_tier = "C"

    return {
        "version": 1,
        "partial_runtime_verified": partial_verified,
        "strong_partial": strong_partial,
        "stable_window": stable,
        "screenshot_count": len(captured),
        "gameplay_candidate_count": gameplay_hits,
        "min_confidence_tier": min_tier,
        "summary_ar": (
            "تشغيل مستقر مع لقطات runtime — أدلة gameplay جزئية (تحقق مؤسسي غير مكتمل)"
            if strong_partial
            else (
                "تشغيل مستقر مع لقطات — ملاحظة L4 جزئية"
                if partial_verified
                else (
                    "تشغيل ملاحظة — مراجعة examiner مطلوبة"
                    if runtime_observed
                    else ""
                )
            )
        ),
        "examiner_signoff_recommended": True,
    }


def apply_confidence_tier_floor(
    tier: Dict[str, Any],
    promotion: Dict[str, Any],
) -> Dict[str, Any]:
    """Raise tier to promotion minimum without lowering existing high tiers."""
    floor = promotion.get("min_confidence_tier")
    if not floor or not isinstance(tier, dict):
        return tier
    order = {"A": 4, "B": 3, "C": 2, "D": 1}
    current = str(tier.get("tier") or "D").upper()
    target = str(floor).upper()
    if order.get(target, 0) > order.get(current, 0):
        tier = dict(tier)
        tier["tier"] = target
        tier["tier_label"] = {
            "A": "runtime_verified",
            "B": "export_verified",
            "C": "static_inference",
            "D": "examiner_heavy",
        }.get(target, tier.get("tier_label"))
        tier["promoted_by"] = "runtime_evidence_promotion_v1"
        if target in ("A", "B"):
            tier["confidence_score"] = max(float(tier.get("confidence_score") or 0), 0.72)
            tier["confidence_pct"] = max(int(tier.get("confidence_pct") or 0), 72)
        tier["examiner_signoff_required"] = True
        tier["human_signoff_mandatory"] = True
    return tier
