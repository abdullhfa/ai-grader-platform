"""
Runtime Claim Contract — L0–L3 constitutional envelope.

Every runtime-related claim MUST carry:
  authority_level, ambiguity_state, corroboration_source, claim_boundary

Principle: runtime observation ≠ criterion authority.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

FREEZE_JSON = Path(__file__).resolve().parent / "calibration" / "GOVERNANCE_FREEZE_v1.json"

REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "claim_type",
    "authority_level",
    "ambiguity_state",
    "corroboration_source",
    "claim_boundary",
    "language_contract",
)

FORBIDDEN_PHRASES_EN = (
    "game verified",
    "gameplay verified",
    "criterion confirmed",
    "runtime validated",
    "game works",
    "testing completed",
    "criterion achieved from visual",
)

ALLOWED_PHRASING_AR = (
    "أدلة بصرية/زمنية موجهة للتشغيل تشير إلى نشاط لعب محتمل",
    "سلطة المعيار تبقى بشرية-محكومة",
    "لم تُستنتَج تلقائياً",
)


def _load_freeze() -> Dict[str, Any]:
    try:
        with open(FREEZE_JSON, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"max_auto_runtime_level": 3}


def _claim_boundary_for_level(level: int) -> str:
    freeze = _load_freeze()
    max_auto = int(freeze.get("max_auto_runtime_level") or 3)
    if level <= 0:
        return "no_runtime_claims_permitted"
    if level <= max_auto:
        return "advisory_corroborative_only"
    if level == 4:
        return "partial_runtime_observation"
    return "governed_human_review"


def _language_contract_for_tier(tier: str) -> Dict[str, str]:
    from app.l2_l3_corroborative_runtime import (
        INSTITUTIONAL_PHRASING_AR,
        INSTITUTIONAL_PHRASING_EN,
    )

    if tier in ("L2", "L3"):
        return {
            "allowed_en": INSTITUTIONAL_PHRASING_EN,
            "allowed_ar": INSTITUTIONAL_PHRASING_AR,
            "forbidden_en": "; ".join(FORBIDDEN_PHRASES_EN[:4]),
        }
    return {
        "allowed_en": "runtime-capable artifact detected — not executed",
        "allowed_ar": "artifact مُرصد — لم يُتحقق من التشغيل",
        "forbidden_en": "; ".join(FORBIDDEN_PHRASES_EN[:3]),
    }


def make_runtime_claim(
    *,
    claim_id: str,
    claim_type: str,
    authority_level: str,
    ambiguity_state: str,
    corroboration_source: str,
    claim_boundary: Optional[str] = None,
    detail_ar: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one contract-compliant runtime claim."""
    lvl_num = 0
    m = re.search(r"L(\d+)", authority_level or "")
    if m:
        lvl_num = int(m.group(1))
    boundary = claim_boundary or _claim_boundary_for_level(lvl_num)
    tier = authority_level if authority_level.startswith("L") else f"L{lvl_num}"
    return {
        "claim_id": claim_id,
        "claim_type": claim_type,
        "authority_level": authority_level,
        "ambiguity_state": ambiguity_state,
        "corroboration_source": corroboration_source,
        "claim_boundary": boundary,
        "language_contract": _language_contract_for_tier(tier),
        "detail_ar": detail_ar,
        "criterion_authority_auto_inferred": False,
        "meta": meta or {},
    }


def build_runtime_claims_registry(
    inventory: Mapping[str, Any],
    *,
    project_profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Collect all runtime-related claims from artifact inventory into one registry.
    """
    inv = dict(inventory or {})
    claims: List[Dict[str, Any]] = []
    seq = 0

    def add(**kwargs: Any) -> None:
        nonlocal seq
        seq += 1
        cid = kwargs.pop("claim_id", None) or f"rtc_{seq:03d}"
        claims.append(make_runtime_claim(claim_id=cid, **kwargs))

    rt_level = inv.get("runtime_evidence_level") or {}
    lvl = int(rt_level.get("level") or 0)
    if lvl >= 1:
        add(
            claim_id="runtime_level",
            claim_type="runtime_evidence_level",
            authority_level=f"L{lvl}",
            ambiguity_state="bounded" if lvl <= 3 else "human_governed",
            corroboration_source="artifact_inventory.compute_runtime_evidence_level",
            detail_ar=str(rt_level.get("note_ar") or rt_level.get("label_ar") or ""),
            meta={"authority": rt_level.get("authority"), "max_auto_level": rt_level.get("max_auto_level", 3)},
        )

    l2l3 = inv.get("l2_l3_corroborative_runtime") or {}
    for shot in l2l3.get("l2_folder_screenshots") or []:
        if not isinstance(shot, dict):
            continue
        add(
            claim_id=f"l2_{shot.get('basename', seq)}",
            claim_type="l2_corroborative_screenshot",
            authority_level="L2",
            ambiguity_state="preserved",
            corroboration_source=str(shot.get("source") or "folder_gameplay_evidence_path"),
            detail_ar=f"لقطة {shot.get('basename')} — corroborative hint only",
            meta={"path": shot.get("path"), "not_inferred": shot.get("not_inferred") or []},
        )

    l3 = l2l3.get("l3_video_evidence") or {}
    if (l3.get("videos_detected") or 0) > 0 or (l3.get("frames_sampled") or 0) > 0:
        add(
            claim_id="l3_video_temporal",
            claim_type="l3_temporal_video_hint",
            authority_level="L3",
            ambiguity_state="preserved",
            corroboration_source="gameplay_video_inference",
            detail_ar=str(l3.get("institutional_label_ar") or "نشاط تشغيلي مُلاحَظ ضمن شروط أدلة محدودة"),
            meta={
                "frames_sampled": l3.get("frames_sampled"),
                "videos_detected": l3.get("videos_detected"),
                "not_inferred": l3.get("not_inferred") or [],
            },
        )

    for item in (inv.get("screenshot_intelligence") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        add(
            claim_type="screenshot_intelligence_hint",
            authority_level="L2",
            ambiguity_state="advisory",
            corroboration_source=str(item.get("source") or "screenshot_intelligence"),
            detail_ar=f"استدلال بصري: {', '.join(item.get('possible_evidence') or [])}",
            meta={"confidence": item.get("confidence"), "mode": item.get("mode")},
        )

    for hint in ((inv.get("gameplay_video_inference") or {}).get("video_analysis") or {}).get("runtime_hints") or []:
        if not isinstance(hint, dict):
            continue
        add(
            claim_type="video_runtime_hint",
            authority_level="L3",
            ambiguity_state="advisory",
            corroboration_source="gameplay_video_inference.runtime_hints",
            detail_ar=str(hint.get("detail") or hint.get("hint_type") or "video hint"),
            meta={
                "hint_authority": hint.get("hint_authority"),
                "corroborated_by": hint.get("corroborated_by") or [],
            },
        )

    for amb in l2l3.get("ambiguity_flags") or []:
        if not isinstance(amb, dict):
            continue
        add(
            claim_type="ambiguity_flag",
            authority_level=f"L{lvl}" if lvl else "L0",
            ambiguity_state="visible",
            corroboration_source="l2_l3_corroborative_runtime._build_ambiguity_flags",
            detail_ar=str(amb.get("message_ar") or amb.get("flag") or ""),
            meta={"flag": amb.get("flag")},
        )

    cross = inv.get("cross_artifact_consistency") or {}
    for amb in cross.get("ambiguities") or []:
        if not isinstance(amb, dict):
            continue
        add(
            claim_type="cross_artifact_ambiguity",
            authority_level=f"L{lvl}" if lvl else "L0",
            ambiguity_state="visible",
            corroboration_source="cross_artifact_consistency",
            detail_ar=str(amb.get("message_ar") or ""),
            meta={"code": amb.get("code"), "severity": amb.get("severity")},
        )

    tc = inv.get("temporal_consistency") or {}
    for sig in tc.get("temporal_consistency_signals") or []:
        if not isinstance(sig, dict):
            continue
        add(
            claim_type="temporal_contradiction",
            authority_level=f"L{lvl}" if lvl else "L0",
            ambiguity_state="downgrade",
            corroboration_source="temporal_consistency_governance",
            detail_ar=str(sig.get("message_ar") or ""),
            meta={"code": sig.get("code"), "effect": "authority_downgrade"},
        )

    mapping = inv.get("authority_mapping") or {}
    if mapping:
        add(
            claim_id="claim_boundary_aggregate",
            claim_type="claim_boundary",
            authority_level=f"L{lvl}" if lvl else "L0",
            ambiguity_state="enforced",
            corroboration_source="evidence_authority_mapping",
            claim_boundary=str(mapping.get("enforcement_mode") or _claim_boundary_for_level(lvl)),
            detail_ar="حدود الصياغة المسموحة/الممنوعة — language contract",
            meta={
                "allowed_sample": (mapping.get("aggregate_allowed_claims_en") or [])[:5],
                "forbidden_sample": (mapping.get("aggregate_forbidden_claims_en") or [])[:5],
            },
        )

    violations = validate_runtime_claims_registry(claims)
    return {
        "version": 1,
        "freeze_id": "GOVERNANCE_FREEZE_v1",
        "claim_count": len(claims),
        "claims": claims,
        "contract_complete": len(violations) == 0,
        "violations": violations,
        "principle_ar": "runtime observation ≠ criterion authority",
        "principle_en": "runtime observation is still not criterion authority",
    }


def validate_runtime_claims_registry(claims: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Return contract violations (empty = all claims compliant)."""
    violations: List[Dict[str, str]] = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            violations.append({"claim_index": str(i), "code": "invalid_claim_type"})
            continue
        for field in REQUIRED_CLAIM_FIELDS:
            if field not in claim or claim[field] in (None, ""):
                violations.append({
                    "claim_id": str(claim.get("claim_id") or i),
                    "code": "missing_required_field",
                    "field": field,
                })
        if claim.get("criterion_authority_auto_inferred"):
            violations.append({
                "claim_id": str(claim.get("claim_id") or i),
                "code": "authority_auto_inferred_forbidden",
            })
        detail = str(claim.get("detail_ar") or "")
        for forbidden in FORBIDDEN_PHRASES_EN:
            if forbidden.lower() in detail.lower():
                violations.append({
                    "claim_id": str(claim.get("claim_id") or i),
                    "code": "forbidden_language_in_claim",
                    "phrase": forbidden,
                })
    return violations


def audit_text_language_contract(text: str) -> List[Dict[str, str]]:
    """Scan arbitrary text for forbidden runtime authority language."""
    if not text or not text.strip():
        return []
    from app.governance_drift_monitor import scan_text_for_drift

    return scan_text_for_drift(text)
