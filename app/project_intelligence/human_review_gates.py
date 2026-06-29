"""
Human review escalation gates — deterministic reliability self-awareness (advisory only).

Does not change achieved, scores, or automated grades.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

HUMAN_REVIEW_GATES_VERSION = "1.1"
ADVISORY_MODE = "governance_signal_only"

Severity = str  # low | medium | high | critical
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_CONFIDENCE_PENALTY = {"low": 0.05, "medium": 0.12, "high": 0.22, "critical": 0.35}

_CROSS_MODAL_DIVERSITY_THRESHOLD = 0.4
_EXCESSIVE_NOISE_FLAG_COUNT = 4
_EXCESSIVE_IGNORE_RATIO = 0.45

# Intake flags indicating archive/read failure (sparse + corrupt → medium packaging escalation)
_CORRUPT_INTAKE_FLAG_NAMES: frozenset[str] = frozenset(
    {
        "archive_corrupted_or_unreadable",
        "archive_extract_failed",
        "truncated_archive_uploaded",
    }
)


def _flag_names(rows: Sequence[Any]) -> List[str]:
    out: List[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            f = row.get("flag")
            if f:
                out.append(str(f))
        elif isinstance(row, str) and row.strip():
            out.append(row.strip())
    return out


def _max_severity(current: Severity, new: Severity) -> Severity:
    if _SEVERITY_RANK.get(new, 0) > _SEVERITY_RANK.get(current, 0):
        return new
    return current


def _is_sparse_corrupt_intake(ctx: ReviewContext) -> bool:
    """
    Empty or near-empty evidence plus corrupt/unreadable archive intake signal.
    Packaging triggers use medium severity instead of critical (review gate inflation control).
    """
    item_count = int(ctx.get("evidence_item_count") or 0)
    if item_count > 2:
        return False
    if bool(ctx.get("has_code_system")) or bool(ctx.get("has_runtime_modalities")):
        return False
    noise = set(ctx.get("submission_noise_flag_names") or [])
    return bool(noise & _CORRUPT_INTAKE_FLAG_NAMES)


def _packaging_severity(ctx: ReviewContext, default: Severity) -> Severity:
    if _is_sparse_corrupt_intake(ctx) and default == "critical":
        return "medium"
    return default


def _sparse_evidence_severity(ctx: ReviewContext, default: Severity) -> Severity:
    if not _is_sparse_corrupt_intake(ctx):
        return default
    if default == "critical":
        return "medium"
    if default == "high":
        return "medium"
    return default


def _insufficiency_flag_names(
    rubric_shadow: Optional[Mapping[str, Any]],
    *,
    criterion_level: Optional[str] = None,
) -> List[str]:
    names: List[str] = []
    if not rubric_shadow:
        return names
    if criterion_level and isinstance(rubric_shadow.get("insufficiency_flags"), list):
        return _flag_names(rubric_shadow.get("insufficiency_flags") or [])
    by_crit = rubric_shadow.get("by_criterion") or {}
    if isinstance(by_crit, dict):
        if criterion_level and criterion_level in by_crit:
            row = by_crit[criterion_level]
            if isinstance(row, dict):
                inner = row.get("insufficiency_flags")
                if isinstance(inner, list):
                    return _flag_names(inner)
        for row in by_crit.values():
            if isinstance(row, dict):
                inner = row.get("insufficiency_flags")
                if isinstance(inner, list):
                    names.extend(_flag_names(inner))
                elif row.get("insufficiency_flags") is None:
                    suf = row.get("sufficient")
                    if suf is False:
                        names.append("criterion_shadow_insufficient")
    return list(dict.fromkeys(names))


ReviewContext = Dict[str, Any]
TriggerFn = Callable[[ReviewContext], Optional[Dict[str, Any]]]


def _trigger_corroboration_conflicts(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    conflicts = ctx.get("corroboration_conflicts") or []
    if not conflicts:
        return None
    return {
        "trigger_id": "corroboration_conflicts",
        "severity": "high",
        "category": "cross_modal_conflict",
        "reason": "corroboration_conflicts_detected",
        "reasoning": "corroboration_conflicts_present_in_runtime_layer",
        "detail_count": len(conflicts),
    }


def _trigger_pattern_hints_only(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    flags = set(ctx.get("insufficiency_flag_names") or [])
    if "pattern_hints_only_insufficient" in flags:
        return {
            "trigger_id": "pattern_hint_only_insufficient",
            "severity": "high",
            "category": "evidence_sufficiency",
            "reason": "pattern_hint_only_insufficient",
            "reasoning": "only_pattern_hints_without_semantic_code_confirmation",
        }
    if "pattern_hints_without_semantic_code" in flags:
        return {
            "trigger_id": "pattern_hints_without_code",
            "severity": "high",
            "category": "evidence_sufficiency",
            "reason": "pattern_hints_without_semantic_code",
            "reasoning": "pattern_hints_present_without_code_system",
        }
    return None


def _trigger_video_only_windows(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    cm_flags = set(ctx.get("cross_modal_noise_flag_names") or [])
    if "video_frames_present_without_temporal_overlap" in cm_flags:
        return {
            "trigger_id": "video_only_windows",
            "severity": "medium",
            "category": "runtime_reliability",
            "reason": "video_only_windows",
            "reasoning": "video_frames_without_multimodal_temporal_overlap",
        }
    return None


def _trigger_runtime_without_system(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    flags = set(ctx.get("insufficiency_flag_names") or [])
    if "runtime_present_without_system_confirmation" in flags:
        return {
            "trigger_id": "runtime_without_system_confirmation",
            "severity": "medium",
            "category": "runtime_reliability",
            "reason": "runtime_present_without_system_confirmation",
            "reasoning": "runtime_evidence_exists_without_corroborated_system_detection",
        }
    rc_flags = set(ctx.get("missing_runtime_corroboration_flag_names") or [])
    if rc_flags:
        return {
            "trigger_id": "insufficient_runtime_confirmation",
            "severity": "medium",
            "category": "runtime_reliability",
            "reason": "insufficient_runtime_confirmation",
            "reasoning": "missing_runtime_corroboration_for_detected_systems",
            "detail_count": len(rc_flags),
        }
    return None


def _trigger_low_cross_modal_diversity(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    try:
        div = float(ctx.get("cross_modal_diversity_score") or 0.0)
    except (TypeError, ValueError):
        div = 0.0
    if div >= _CROSS_MODAL_DIVERSITY_THRESHOLD:
        return None
    has_runtime_modality = bool(ctx.get("has_runtime_modalities"))
    if not has_runtime_modality:
        return None
    return {
        "trigger_id": "low_cross_modal_diversity",
        "severity": "medium",
        "category": "cross_modal_conflict",
        "reason": "cross_modal_diversity_below_threshold",
        "reasoning": "cross_modal_overlap_insufficient",
        "detail": round(div, 4),
    }


def _trigger_rubric_shadow_insufficient(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    if ctx.get("rubric_shadow_sufficient") is False:
        return {
            "trigger_id": "rubric_shadow_insufficient",
            "severity": "medium",
            "category": "evidence_sufficiency",
            "reason": "rubric_sufficiency_shadow_not_met",
            "reasoning": "declarative_sufficiency_contract_not_satisfied",
        }
    flags = set(ctx.get("insufficiency_flag_names") or [])
    if "ocr_video_without_corroboration" in flags:
        return {
            "trigger_id": "ocr_video_without_corroboration",
            "severity": "high",
            "category": "cross_modal_conflict",
            "reason": "ocr_video_without_corroboration",
            "reasoning": "ocr_or_video_present_without_corroboration",
        }
    if "corroboration_conflict_detected" in flags:
        return {
            "trigger_id": "sufficiency_corroboration_conflict",
            "severity": "high",
            "category": "cross_modal_conflict",
            "reason": "cross_modal_conflict_detected",
            "reasoning": "rubric_shadow_reported_corroboration_conflict",
        }
    return None


def _trigger_submission_noise(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    noise = ctx.get("submission_noise_flag_names") or []
    if len(noise) >= _EXCESSIVE_NOISE_FLAG_COUNT:
        return {
            "trigger_id": "excessive_submission_noise",
            "severity": "critical",
            "category": "submission_packaging",
            "reason": "excessive_submission_noise_flags",
            "reasoning": "upload_packaging_noise_may_degrade_automated_evidence_quality",
            "detail_count": len(noise),
        }
    try:
        ratio = float(ctx.get("submission_ignore_ratio") or 0.0)
    except (TypeError, ValueError):
        ratio = 0.0
    if ratio >= _EXCESSIVE_IGNORE_RATIO:
        sev = _packaging_severity(ctx, "critical")
        return {
            "trigger_id": "high_upload_ignore_ratio",
            "severity": sev,
            "category": "submission_packaging",
            "reason": "high_submission_ignore_ratio",
            "reasoning": (
                "large_fraction_of_upload_paths_ignored_by_intake"
                if sev == "critical"
                else "high_ignore_ratio_on_sparse_corrupt_archive_intake"
            ),
            "detail": round(ratio, 4),
        }
    return None


def _trigger_sparse_evidence(ctx: ReviewContext) -> Optional[Dict[str, Any]]:
    item_count = int(ctx.get("evidence_item_count") or 0)
    has_code = bool(ctx.get("has_code_system"))
    has_runtime = bool(ctx.get("has_runtime_modalities"))
    noise_severe = len(ctx.get("submission_noise_flag_names") or []) >= 2
    if item_count <= 2 and not has_code and noise_severe:
        sev = _sparse_evidence_severity(ctx, "critical")
        return {
            "trigger_id": "sparse_evidence_with_upload_noise",
            "severity": sev,
            "category": "evidence_sufficiency",
            "reason": "sparse_evidence_with_upload_noise",
            "reasoning": (
                "very_few_evidence_items_plus_submission_packaging_noise"
                if sev != "medium"
                else "sparse_evidence_with_corrupt_archive_intake"
            ),
            "detail_count": item_count,
        }
    if item_count <= 1 and not has_code and not has_runtime:
        sev = _sparse_evidence_severity(ctx, "high")
        return {
            "trigger_id": "sparse_evidence",
            "severity": sev,
            "category": "evidence_sufficiency",
            "reason": "sparse_evidence_detected",
            "reasoning": (
                "minimal_extracted_evidence_for_reliable_automation"
                if sev != "medium"
                else "sparse_evidence_on_corrupt_or_empty_archive_intake"
            ),
            "detail_count": item_count,
        }
    return None


_TRIGGER_REGISTRY: Tuple[TriggerFn, ...] = (
    _trigger_corroboration_conflicts,
    _trigger_pattern_hints_only,
    _trigger_video_only_windows,
    _trigger_runtime_without_system,
    _trigger_low_cross_modal_diversity,
    _trigger_rubric_shadow_insufficient,
    _trigger_submission_noise,
    _trigger_sparse_evidence,
)


def build_review_context(
    evidence_layer: Optional[Mapping[str, Any]],
    *,
    rubric_shadow: Optional[Mapping[str, Any]] = None,
    criterion_level: Optional[str] = None,
    criterion_rubric_shadow: Optional[Mapping[str, Any]] = None,
) -> ReviewContext:
    """Assemble inputs allowed for gate evaluation (no profile / LLM)."""
    layer = evidence_layer or {}
    rc = layer.get("runtime_corroboration") or {}
    cm = layer.get("cross_modal_corroboration") or {}
    si = layer.get("submission_intake") or {}
    ud = si.get("upload_diagnostics") or {} if isinstance(si, dict) else {}

    items = [it for it in (layer.get("items") or []) if isinstance(it, dict)]
    runtime_types = {"runtime_log", "runtime_screenshot", "video_frame", "ocr_text"}
    has_runtime = any(it.get("evidence_type") in runtime_types for it in items)
    has_code = any(it.get("evidence_type") == "code_system" for it in items)
    pattern_only = bool(items) and all(
        it.get("evidence_type") == "pattern_hint" for it in items
    )

    rubric_layer = rubric_shadow or layer.get("rubric_sufficiency_shadow") or {}
    shadow = criterion_rubric_shadow
    if not shadow and criterion_level and isinstance(rubric_layer, dict):
        row = (rubric_layer.get("by_criterion") or {}).get(criterion_level)
        if isinstance(row, dict):
            shadow = row

    insuff_names: List[str] = []
    rubric_sufficient: Optional[bool] = None
    if isinstance(shadow, dict):
        insuff_names = _flag_names(shadow.get("insufficiency_flags") or [])
        if shadow.get("sufficient") is not None:
            rubric_sufficient = bool(shadow.get("sufficient"))
        sr = shadow.get("sufficiency_result") or {}
        if isinstance(sr, dict) and sr.get("sufficient") is not None:
            rubric_sufficient = bool(sr.get("sufficient"))
    elif criterion_level:
        insuff_names = _insufficiency_flag_names(rubric_layer, criterion_level=criterion_level)
    else:
        insuff_names = _insufficiency_flag_names(rubric_layer)

    return {
        "corroboration_conflicts": list(rc.get("corroboration_conflicts") or []),
        "missing_runtime_corroboration_flag_names": _flag_names(
            rc.get("missing_runtime_corroboration_flags") or []
        ),
        "cross_modal_diversity_score": cm.get("cross_modal_diversity_score"),
        "cross_modal_noise_flag_names": _flag_names(cm.get("cross_modal_noise_flags") or []),
        "submission_noise_flag_names": _flag_names(si.get("submission_noise_flags") or []),
        "submission_ignore_ratio": ud.get("ignore_ratio") if isinstance(ud, dict) else None,
        "insufficiency_flag_names": insuff_names,
        "rubric_shadow_sufficient": rubric_sufficient,
        "evidence_item_count": len(items),
        "has_code_system": has_code,
        "has_runtime_modalities": has_runtime,
        "pattern_hint_only_submission": pattern_only,
    }


def evaluate_review_triggers(ctx: ReviewContext) -> List[Dict[str, Any]]:
    """Run declarative trigger registry; return fired triggers."""
    fired: List[Dict[str, Any]] = []
    for fn in _TRIGGER_REGISTRY:
        hit = fn(ctx)
        if hit:
            fired.append(hit)
    return fired


def _deterministic_review_confidence(fired: List[Dict[str, Any]]) -> float:
    penalty = 0.0
    for row in fired:
        sev = str(row.get("severity") or "low")
        penalty += _CONFIDENCE_PENALTY.get(sev, 0.08)
    return round(max(0.0, min(1.0, 1.0 - penalty)), 4)


def aggregate_human_review(
    fired: List[Dict[str, Any]],
    *,
    criterion_level: Optional[str] = None,
) -> Dict[str, Any]:
    """Build human_review_required + review_reasoning + categories."""
    if not fired:
        return {
            "human_review_required": {
                "required": False,
                "severity": "low",
                "reasons": [],
            },
            "review_reasoning": {"reasoning": ["automated_evidence_stack_within_advisory_thresholds"]},
            "review_confidence": 1.0,
            "review_categories": [],
            "triggers_fired": [],
            "advisory_mode": ADVISORY_MODE,
            "criterion_level": criterion_level,
        }

    severity: Severity = "low"
    reasons: List[str] = []
    reasoning: List[str] = []
    categories: List[str] = []

    for row in fired:
        severity = _max_severity(severity, str(row.get("severity") or "medium"))
        reason = row.get("reason")
        if reason and reason not in reasons:
            reasons.append(str(reason))
        rsn = row.get("reasoning")
        if rsn and rsn not in reasoning:
            reasoning.append(str(rsn))
        cat = row.get("category")
        if cat and cat not in categories:
            categories.append(str(cat))

    required = _SEVERITY_RANK.get(severity, 0) >= _SEVERITY_RANK["medium"]
    confidence = _deterministic_review_confidence(fired)

    return {
        "human_review_required": {
            "required": required,
            "severity": severity,
            "reasons": sorted(reasons),
        },
        "review_reasoning": {"reasoning": reasoning},
        "review_confidence": confidence,
        "review_categories": sorted(categories),
        "triggers_fired": fired,
        "advisory_mode": ADVISORY_MODE,
        "criterion_level": criterion_level,
    }


def evaluate_human_review_gates(
    evidence_layer: Optional[Mapping[str, Any]],
    *,
    rubric_shadow: Optional[Mapping[str, Any]] = None,
    criterion_level: Optional[str] = None,
    criterion_rubric_shadow: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer- or criterion-level human review gate evaluation."""
    ctx = build_review_context(
        evidence_layer,
        rubric_shadow=rubric_shadow,
        criterion_level=criterion_level,
        criterion_rubric_shadow=criterion_rubric_shadow,
    )
    fired = evaluate_review_triggers(ctx)
    out = aggregate_human_review(fired, criterion_level=criterion_level)
    out["version"] = HUMAN_REVIEW_GATES_VERSION
    return out


def build_evidence_layer_human_review(
    evidence_layer: Mapping[str, Any],
) -> Dict[str, Any]:
    """Submission-wide escalation summary."""
    rubric_shadow = evidence_layer.get("rubric_sufficiency_shadow")
    layer_eval = evaluate_human_review_gates(
        evidence_layer,
        rubric_shadow=rubric_shadow if isinstance(rubric_shadow, dict) else None,
    )
    by_criterion: Dict[str, Any] = {}
    rub = rubric_shadow if isinstance(rubric_shadow, dict) else {}
    for lvl, row in (rub.get("by_criterion") or {}).items():
        if not lvl:
            continue
        by_criterion[str(lvl)] = evaluate_human_review_gates(
            evidence_layer,
            rubric_shadow=rub,
            criterion_level=str(lvl),
            criterion_rubric_shadow=row if isinstance(row, dict) else None,
        )
    return {
        "version": HUMAN_REVIEW_GATES_VERSION,
        "advisory_mode": ADVISORY_MODE,
        "submission": {
            "human_review_required": layer_eval.get("human_review_required"),
            "review_confidence": layer_eval.get("review_confidence"),
            "review_categories": layer_eval.get("review_categories"),
            "review_reasoning": layer_eval.get("review_reasoning"),
            "triggers_fired_count": len(layer_eval.get("triggers_fired") or []),
        },
        "by_criterion": by_criterion,
        "layer_evaluation": layer_eval,
    }


def attach_human_review_gates(
    grading_result: Dict[str, Any],
    evidence_layer: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Attach human review gates to evidence_layer and per-criterion academic snapshots.
    Does not modify achieved.
    """
    block = build_evidence_layer_human_review(evidence_layer)
    evidence_layer["human_review_gates"] = block

    by_crit = block.get("by_criterion") or {}
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        lvl = str(cr.get("criteria_level") or "")
        crit_eval = by_crit.get(lvl)
        if not crit_eval:
            crit_eval = evaluate_human_review_gates(
                evidence_layer,
                criterion_level=lvl,
            )
        snap = cr.get("academic_snapshot")
        if not isinstance(snap, dict):
            snap = {}
            cr["academic_snapshot"] = snap
        snap["human_review_required"] = crit_eval.get("human_review_required")
        snap["review_reasoning"] = crit_eval.get("review_reasoning")
        snap["review_confidence"] = crit_eval.get("review_confidence")
        snap["review_categories"] = crit_eval.get("review_categories")

    return block
