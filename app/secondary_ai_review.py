"""Independent, selective second-opinion review for sensitive BTEC decisions."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from app.ai_provider import AIProvider
from app.llm_json_utils import parse_llm_grading_json


SECONDARY_REVIEW_VERSION = "1.0"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _short_level(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text.split(".")[-1] if "." in text else text


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"true", "yes", "1", "نعم", "متحقق"}


def _confidence(row: Dict[str, Any]) -> Optional[float]:
    candidates = [
        row.get("review_confidence"),
        (row.get("academic_snapshot") or {}).get("review_confidence"),
        (row.get("confidence") or {}).get("score") if isinstance(row.get("confidence"), dict) else row.get("confidence"),
    ]
    for value in candidates:
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if score > 1:
            score /= 100
        return max(0.0, min(1.0, score))
    return None


def select_sensitive_criteria(
    grading_result: Dict[str, Any], *, low_confidence_threshold: float = 0.65
) -> List[str]:
    """Select M/D, low-confidence, gate-blocked, and internally disputed criteria."""
    selected: List[str] = []
    reliability = grading_result.get("ai_reliability") or {}
    disputed = {
        _short_level(item.get("criterion") if isinstance(item, dict) else item)
        for item in (reliability.get("disagreements") or [])
    }
    gate_keys = (
        "runtime_gate_block",
        "version_gate_block",
        "pro_gameplay_governance_hold",
        "evidence_coverage_block",
        "secondary_review_hold",
    )
    for row in grading_result.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        level = str(row.get("criteria_level") or "").strip()
        short = _short_level(level)
        confidence = _confidence(row)
        is_sensitive_band = short.startswith(("M", "D"))
        include_low_pass = _env_bool("SECONDARY_REVIEW_INCLUDE_LOW_CONFIDENCE_PASS", False)
        is_low_confidence = (
            confidence is not None
            and confidence < low_confidence_threshold
            and (not short.startswith("P") or include_low_pass)
        )
        is_gate_blocked = any(bool(row.get(key)) for key in gate_keys)
        if is_sensitive_band or is_low_confidence or is_gate_blocked or short in disputed:
            if level and level not in selected:
                selected.append(level)
    return selected


def _truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = max(1, (limit - 90) // 2)
    return text[:half] + "\n\n[… اختصار آلي مع حفظ البداية والنهاية …]\n\n" + text[-half:]


def _criterion_specs(criteria: Iterable[Dict[str, Any]], selected: List[str]) -> List[Dict[str, Any]]:
    selected_short = {_short_level(v) for v in selected}
    specs: List[Dict[str, Any]] = []
    for item in criteria:
        level = str(item.get("criteria_level") or "").strip()
        if _short_level(level) not in selected_short:
            continue
        specs.append(
            {
                "criterion": level,
                "description": item.get("criteria_description") or "",
                "key_points": item.get("key_points") or "",
            }
        )
    return specs


def _runtime_facts(grading_result: Dict[str, Any], artifact_inventory: Dict[str, Any]) -> Dict[str, Any]:
    package = grading_result.get("runtime_evidence_package") or {}
    if isinstance(package, dict) and isinstance(package.get("package"), dict):
        package = package["package"]
    gameplay = artifact_inventory.get("gameplay_evidence") or {}
    inference = artifact_inventory.get("gameplay_video_inference") or {}
    return {
        "runtime_status": package.get("runtime_status") if isinstance(package, dict) else None,
        "runtime_evidence_strength": package.get("runtime_evidence_strength") if isinstance(package, dict) else None,
        "runtime_evidence_level": artifact_inventory.get("runtime_evidence_level"),
        "gameplay_evidence_level": gameplay.get("level") if isinstance(gameplay, dict) else None,
        "gameplay_entered": inference.get("gameplay_entered") if isinstance(inference, dict) else None,
        "video_present": bool(artifact_inventory.get("video_files") or artifact_inventory.get("videos")),
    }


def _build_messages(
    *,
    selected: List[str],
    grading_criteria: List[Dict[str, Any]],
    student_text: str,
    reference_solution: Dict[str, Any],
    grading_result: Dict[str, Any],
    artifact_inventory: Dict[str, Any],
) -> List[Dict[str, str]]:
    try:
        max_chars = max(20_000, int(os.getenv("SECONDARY_REVIEW_MAX_CHARS", "140000")))
    except ValueError:
        max_chars = 140_000
    guide = reference_solution.get("markdown_guide") or reference_solution.get("content") or ""
    payload = {
        "criteria_to_review": _criterion_specs(grading_criteria, selected),
        "deterministic_runtime_facts": _runtime_facts(grading_result, artifact_inventory),
        "student_submission": _truncate_middle(student_text or "", max_chars),
        "assignment_guide": _truncate_middle(str(guide or ""), 45_000),
    }
    system = (
        "أنت مراجع ثانٍ مستقل لمعايير Pearson BTEC. قيّم فقط المعايير المحددة من الأدلة المرسلة، "
        "من دون تخمين ومن دون افتراض قرار المصحح الأساسي. حقائق التشغيل الحتمية ملزمة ولا يجوز تجاوزها. "
        "أعد JSON فقط بالشكل: {\"criteria_reviews\":[{\"criterion\":\"M1\","
        "\"achieved\":true,\"confidence\":0.0,\"evidence_refs\":[\"...\"],"
        "\"reasoning\":\"...\",\"missing_evidence\":[\"...\"]}]}. "
        "الثقة من 0 إلى 1، واذكر موضع الدليل أو النص الدال قدر الإمكان."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def run_secondary_review(
    grading_result: Dict[str, Any],
    *,
    student_text: str,
    grading_criteria: List[Dict[str, Any]],
    reference_solution: Optional[Dict[str, Any]] = None,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    reviewer_provider: Optional[Any] = None,
    force_enabled: bool = False,
) -> Dict[str, Any]:
    """Attach an independent DeepSeek review; disagreement creates HOLD, never an override."""
    enabled = force_enabled or _env_bool("SECONDARY_REVIEW_ENABLED", False)
    primary = grading_result.get("primary_ai_grader") or {
        "provider": os.getenv("AI_PROVIDER", "gemini"),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-pro"),
    }
    resolution_policy = (os.getenv("SECONDARY_REVIEW_DISAGREEMENT_POLICY") or "primary").strip().lower()
    if resolution_policy not in {"primary", "authoritative", "hold"}:
        resolution_policy = "primary"
    audit: Dict[str, Any] = {
        "version": SECONDARY_REVIEW_VERSION,
        "enabled": enabled,
        "primary": primary,
        "reviewer": {"provider": "deepseek", "model": os.getenv("DEEPSEEK_REVIEW_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash-vision-exp")},
        "status": "DISABLED",
        "selected_criteria": [],
        "agreements": [],
        "disagreements": [],
        "deterministic_overrides": [],
        "resolution_policy": resolution_policy,
        "hold_required": False,
    }
    grading_result["secondary_ai_review"] = audit
    if not enabled:
        return audit
    if str(primary.get("provider") or "").lower() != "gemini" and not force_enabled:
        audit["status"] = "SKIPPED_PRIMARY_NOT_GEMINI"
        return audit

    try:
        threshold = float(os.getenv("SECONDARY_REVIEW_LOW_CONFIDENCE", "0.65"))
    except ValueError:
        threshold = 0.65
    selected = select_sensitive_criteria(grading_result, low_confidence_threshold=threshold)
    audit["selected_criteria"] = selected
    if not selected:
        audit["status"] = "NO_SENSITIVE_CRITERIA"
        grading_result["grade_decision_status"] = "PRIMARY_ONLY_NO_SENSITIVE_CRITERIA"
        return audit

    provider = reviewer_provider or AIProvider(
        provider="deepseek", model=str(audit["reviewer"]["model"])
    )
    try:
        response = provider.chat_completion(
            _build_messages(
                selected=selected,
                grading_criteria=grading_criteria,
                student_text=student_text,
                reference_solution=reference_solution or {},
                grading_result=grading_result,
                artifact_inventory=artifact_inventory or {},
            ),
            temperature=0.0,
            max_tokens=8000,
            response_format={"type": "json_object"},
            seed=None,
        )
        parsed = parse_llm_grading_json(response)
    except Exception as exc:
        audit["status"] = "REVIEW_UNAVAILABLE"
        audit["error"] = str(exc)[:500]
        grading_result["grade_decision_status"] = "PRIMARY_ONLY_REVIEW_UNAVAILABLE"
        return audit

    reviews = parsed.get("criteria_reviews") or []
    by_short = {
        _short_level(item.get("criterion")): item
        for item in reviews
        if isinstance(item, dict) and item.get("criterion")
    }
    for row in grading_result.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        level = str(row.get("criteria_level") or "")
        if level not in selected:
            continue
        review = by_short.get(_short_level(level))
        if not review:
            continue
        reviewer_achieved = _as_bool(review.get("achieved"))
        authoritative_achieved = bool(row.get("achieved"))
        primary_decision = row.get("primary_ai_decision") or {}
        primary_ai_achieved = _as_bool(
            primary_decision.get("achieved", authoritative_achieved)
        )
        agreement = reviewer_achieved == primary_ai_achieved
        row_audit = {
            "provider": "deepseek",
            "model": getattr(provider, "model", audit["reviewer"]["model"]),
            "reviewer_achieved": reviewer_achieved,
            "primary_ai_achieved": primary_ai_achieved,
            "authoritative_achieved": authoritative_achieved,
            "agreement": agreement,
            "confidence": review.get("confidence"),
            "reasoning": str(review.get("reasoning") or ""),
            "evidence_refs": review.get("evidence_refs") or [],
            "missing_evidence": review.get("missing_evidence") or [],
        }
        row["secondary_ai_review"] = row_audit
        target = "agreements" if agreement else "disagreements"
        audit[target].append({"criterion": level, **row_audit})
        if agreement and reviewer_achieved != authoritative_achieved:
            audit["deterministic_overrides"].append(
                {
                    "criterion": level,
                    "models_achieved": reviewer_achieved,
                    "authoritative_achieved": authoritative_achieved,
                    "reason": row.get("governance_adjustment_ar")
                    or row.get("runtime_gate_reason")
                    or row.get("feedback")
                    or "deterministic_rule_override",
                }
            )
        if not agreement and resolution_policy == "hold":
            row["secondary_review_hold"] = True
        elif not agreement:
            row["secondary_review_auto_resolved"] = resolution_policy

    reviewed = len(audit["agreements"]) + len(audit["disagreements"])
    audit["reviewed_count"] = reviewed
    audit["unreviewed_criteria"] = [
        level for level in selected if _short_level(level) not in by_short
    ]
    if audit["disagreements"] and resolution_policy == "hold":
        audit["status"] = "HOLD"
        audit["hold_required"] = True
        grading_result["grade_decision_status"] = "HOLD"
        grading_result["grade_level_provisional"] = grading_result.get("grade_level")
        grading_result["official_grade_provisional"] = True
        grading_result["human_review_required"] = True
    elif audit["disagreements"]:
        audit["status"] = (
            "AUTO_RESOLVED_PRIMARY"
            if resolution_policy == "primary"
            else "AUTO_RESOLVED_AUTHORITATIVE"
        )
        grading_result["grade_decision_status"] = audit["status"]
        grading_result["official_grade_provisional"] = False
        grading_result["human_review_required"] = False
        for row in grading_result.get("criteria_results") or []:
            if isinstance(row, dict):
                row.pop("secondary_review_hold", None)
    elif audit["unreviewed_criteria"]:
        audit["status"] = "PARTIAL_REVIEW"
        grading_result["grade_decision_status"] = "PRIMARY_ONLY_PARTIAL_REVIEW"
    elif audit["deterministic_overrides"]:
        audit["status"] = "CONFIRMED_MODELS_WITH_RULE_OVERRIDE"
        grading_result["grade_decision_status"] = audit["status"]
        grading_result["official_grade_provisional"] = False
        grading_result["human_review_required"] = False
    else:
        audit["status"] = "CONFIRMED"
        grading_result["grade_decision_status"] = "CONFIRMED_BY_SECONDARY_REVIEW"
        grading_result["official_grade_provisional"] = False
    return audit
