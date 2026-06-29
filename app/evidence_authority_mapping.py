"""
Evidence-Authority Mapping Layer — formal allowed-claims registry.

Principle: claims exceeding authority level are blocked, not silently upgraded.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Evidence type → max runtime level → allowed claim IDs
EVIDENCE_AUTHORITY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "executable_detected": {
        "max_level": 1,
        "authority": "artifact_acknowledgment_only",
        "allowed_claims_en": [
            "runtime_capable_artifact_exists",
            "executable_submitted_not_executed",
        ],
        "allowed_claims_ar": [
            "artifact تنفيذي قابل للتشغيل مُرصد",
            "ملف تنفيذي مرفق — لم يُشغَّل",
        ],
        "forbidden_claims_en": [
            "game_verified",
            "game_works",
            "criterion_confirmed",
            "runtime_behaviour_verified",
        ],
    },
    "hud_screenshot_inference": {
        "max_level": 2,
        "authority": "advisory_visual_inference",
        "allowed_claims_en": [
            "possible_scoring_mechanic",
            "possible_ui_hud",
            "gameplay_visual_candidate",
        ],
        "allowed_claims_ar": [
            "احتمال وجود نظام نقاط/واجهة HUD",
            "مرشّح بصري — ليس verification",
        ],
        "forbidden_claims_en": [
            "score_system_verified",
            "gameplay_confirmed",
            "criterion_operationally_confirmed",
        ],
    },
    "gameplay_video_detected": {
        "max_level": 3,
        "authority": "advisory_video_inference",
        "allowed_claims_en": [
            "inferred_gameplay_activity",
            "gameplay_footage_candidate",
            "gameplay_activity_inferred",
            "mechanic_visually_suggested",
            "runtime_hints_observed",
        ],
        "allowed_claims_ar": [
            "نشاط لعب مُستدَل من footage — استشاري",
            "footage مرشّح — لم يُتحقق من التشغيل",
            "mechanic مقترح بصرياً — advisory",
        ],
        "forbidden_claims_en": [
            "game_verified",
            "testing_completed",
            "runtime_behaviour_verified",
            "gameplay_verified",
            "game_completed",
            "mechanic_confirmed",
            "runtime_validated",
        ],
    },
    "temporal_video_inference": {
        "max_level": 3,
        "authority": "temporal_advisory_inference",
        "allowed_claims_en": [
            "temporal_continuity_observed",
            "runtime_hints_observed",
            "gameplay_activity_inferred",
        ],
        "allowed_claims_ar": [
            "استمرارية temporal مرصودة — advisory",
            "runtime hints — بدون validation",
        ],
        "forbidden_claims_en": [
            "gameplay_verified",
            "runtime_validated",
            "criterion_operationally_confirmed",
        ],
    },
    "source_code_inspection": {
        "max_level": 2,
        "authority": "static_code_analysis",
        "allowed_claims_en": [
            "implementation_candidate",
            "code_inspected_without_execution",
        ],
        "allowed_claims_ar": [
            "مرشّح تنفيذ من الكود — بدون تشغيل",
            "فُحص الكود ساكناً",
        ],
        "forbidden_claims_en": [
            "game_tested",
            "runtime_observed",
            "criterion_confirmed",
        ],
    },
    "documentation_analyzed": {
        "max_level": 2,
        "authority": "documentary_analysis",
        "allowed_claims_en": [
            "design_documentation_analyzed",
            "testing_plan_described",
            "evidence_partially_supports",
        ],
        "allowed_claims_ar": [
            "توثيق/تصميم تم تحليله",
            "أدلة جزئية — تحتاج corroboration",
        ],
        "forbidden_claims_en": [
            "game_verified",
            "testing_completed",
            "criterion_operationally_confirmed",
        ],
    },
    "runtime_sandbox_observation": {
        "max_level": 4,
        "authority": "partial_runtime_observation",
        "allowed_claims_en": [
            "executable_launched_in_sandbox",
            "limited_runtime_observations_collected",
        ],
        "allowed_claims_ar": [
            "تشغيل محدود في sandbox — ليس verdict معيار",
        ],
        "forbidden_claims_en": [
            "criterion_verified_automatically",
            "all_requirements_confirmed",
        ],
    },
    "human_review": {
        "max_level": 5,
        "authority": "governed_human_review",
        "allowed_claims_en": [
            "authoritative_confirmation",
            "human_verified_replay",
        ],
        "allowed_claims_ar": [
            "تأكيد بشري موثّق — سلطة مؤسسية",
        ],
        "forbidden_claims_en": [],
    },
}

# Global forbidden → allowed phrasing (en + ar fragments)
FORBIDDEN_CLAIM_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\bgame\s+verified\b", "gameplay evidence observed", "game verified"),
    (r"\bgameplay\s+confirmed\b", "gameplay visually inferred (advisory)", "gameplay confirmed"),
    (r"\bcriterion\s+confirmed\b", "evidence partially supports", "criterion confirmed"),
    (r"\bgame\s+works\b", "runtime-capable artifact detected", "game works"),
    (r"\btesting\s+completed\b", "testing evidence submitted", "testing completed"),
    (r"\bruntime\s+behaviour\s+verified\b", "runtime behaviour inferred from available evidence", "runtime verified"),
    (r"اللعبة\s+تعمل\s+وت?[مم]?\s*تحقق", "artifact تنفيذي مُرصد — بدون تحقق تشغيل", "اللعبة تعمل"),
    (r"تم\s+التحقق\s+من\s+التشغيل", "لم يُتحقق من التشغيل", "تم التحقق من التشغيل"),
    (r"المعيار\s+مؤكد", "أدلة جزئية تدعم المعيار", "المعيار مؤكد"),
    (r"\bgameplay\s+verified\b", "gameplay activity inferred", "gameplay verified"),
    (r"\bgame\s+completed\b", "gameplay footage candidate", "game completed"),
    (r"\bmechanic\s+confirmed\b", "mechanic visually suggested", "mechanic confirmed"),
    (r"\bruntime\s+validated\b", "runtime hints observed", "runtime validated"),
    (r"تم\s+التحقق\s+من\s+اللعب", "نشاط لعب مُستدَل — advisory", "gameplay verified ar"),
    (r"اختبار\s+مكتمل", "أدلة اختبار مُقدَّمة", "اختبار مكتمل"),
]


def _active_evidence_types(inventory: Dict[str, Any]) -> List[str]:
    types: List[str] = []
    rt = inventory.get("runtime_artifacts") or {}
    if rt.get("executables_detected"):
        types.append("executable_detected")
    if (inventory.get("embedded_screenshots") or {}).get("count", 0) > 0:
        types.append("hud_screenshot_inference")
    if (inventory.get("screenshot_intelligence") or {}).get("items"):
        if "hud_screenshot_inference" not in types:
            types.append("hud_screenshot_inference")
    if rt.get("gameplay_video_detected"):
        types.append("gameplay_video_detected")
    gvi = inventory.get("gameplay_video_inference") or {}
    if (gvi.get("videos_analyzed") or 0) > 0:
        if "gameplay_video_detected" not in types:
            types.append("gameplay_video_detected")
        hints = (gvi.get("video_analysis") or {}).get("runtime_hints") or []
        if hints:
            types.append("temporal_video_inference")
    if inventory.get("has_source_code_artifacts"):
        types.append("source_code_inspection")
    if (inventory.get("documentation") or {}).get("files"):
        types.append("documentation_analyzed")
    return types


def build_authority_mapping(
    inventory: Dict[str, Any],
    *,
    project_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build formal evidence → allowed claims mapping for a submission."""
    active = _active_evidence_types(inventory)
    rt_level = inventory.get("runtime_evidence_level") or {}
    current_level = int(rt_level.get("level") or 0)

    by_type: List[Dict[str, Any]] = []
    all_allowed_en: Set[str] = set()
    all_forbidden_en: Set[str] = set()

    for etype in active:
        reg = EVIDENCE_AUTHORITY_REGISTRY.get(etype)
        if not reg:
            continue
        max_lvl = int(reg.get("max_level") or 0)
        permitted = current_level >= 0  # always list; enforcement via max_level
        entry = {
            "evidence_type": etype,
            "authority": reg.get("authority"),
            "max_level": max_lvl,
            "current_level": current_level,
            "claims_permitted": permitted and current_level <= max_lvl,
            "allowed_claims_en": list(reg.get("allowed_claims_en") or []),
            "allowed_claims_ar": list(reg.get("allowed_claims_ar") or []),
            "forbidden_claims_en": list(reg.get("forbidden_claims_en") or []),
        }
        by_type.append(entry)
        all_allowed_en.update(entry["allowed_claims_en"])
        all_forbidden_en.update(entry["forbidden_claims_en"])

    return {
        "version": 1,
        "runtime_evidence_level": current_level,
        "active_evidence_types": active,
        "by_type": by_type,
        "aggregate_allowed_claims_en": sorted(all_allowed_en),
        "aggregate_forbidden_claims_en": sorted(all_forbidden_en),
        "enforcement_mode": "block_overclaim_drift",
        "note_ar": (
            "أي claim يتجاوز max_level لنوع evidence يُعتبر overclaim ويُرفض في الصياغة الرسمية."
        ),
    }


def check_claim_authority(
    claim_text: str,
    *,
    max_level: int = 3,
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Return whether claim_text stays within authority bounds.
    Does not modify grades — governance signal only.
    """
    text = (claim_text or "").strip()
    if not text:
        return {"allowed": True, "violations": [], "sanitized_text": text}

    if inventory:
        rt_level = inventory.get("runtime_evidence_level") or {}
        max_level = min(max_level, int(rt_level.get("level") or 0))

    violations: List[Dict[str, str]] = []
    lower = text.lower()
    for etype in _active_evidence_types(inventory or {}):
        reg = EVIDENCE_AUTHORITY_REGISTRY.get(etype, {})
        for forbidden in reg.get("forbidden_claims_en") or []:
            if forbidden.replace("_", " ") in lower or forbidden in lower:
                violations.append({
                    "type": "registry_forbidden",
                    "evidence_type": etype,
                    "phrase": forbidden,
                })

    for pattern, replacement, label in FORBIDDEN_CLAIM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append({
                "type": "language_contract",
                "phrase": label,
                "suggested_replacement": replacement,
            })

    return {
        "allowed": len(violations) == 0,
        "violations": violations,
        "sanitized_text": sanitize_claim_text(text, inventory=inventory),
        "max_level_applied": max_level,
    }


def sanitize_claim_text(
    text: str,
    *,
    inventory: Optional[Dict[str, Any]] = None,
) -> str:
    """Replace forbidden institutional phrasing with contract-safe alternatives."""
    out = text
    for pattern, replacement, _label in FORBIDDEN_CLAIM_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def format_authority_mapping_for_grading(mapping: Dict[str, Any]) -> str:
    """Inject bounded claim vocabulary into AI grader context."""
    if not mapping.get("by_type"):
        return ""

    lines = [
        "═══════════════════════════════════════════════════════════",
        "[Evidence-Authority Mapping | claims exceeding level BLOCKED]",
        "═══════════════════════════════════════════════════════════",
        f"• runtime_evidence_level: L{mapping.get('runtime_evidence_level', 0)}",
    ]
    for entry in mapping.get("by_type") or []:
        allowed = ", ".join(entry.get("allowed_claims_en") or [])[:120]
        forbidden = ", ".join(entry.get("forbidden_claims_en") or [])[:120]
        lines.append(
            f"• {entry.get('evidence_type')} (max L{entry.get('max_level')}): "
            f"ALLOWED: {allowed}"
        )
        if forbidden:
            lines.append(f"  FORBIDDEN: {forbidden}")
    lines.append(
        "• استخدم: «evidence partially supports» / «runtime-capable artifact detected» — "
        "لا: «game verified» / «criterion confirmed»."
    )
    lines.append("═══════════════════════════════════════════════════════════\n")
    return "\n".join(lines)
