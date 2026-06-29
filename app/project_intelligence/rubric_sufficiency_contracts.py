"""
Declarative rubric sufficiency contracts — deterministic criterion-level evidence adequacy.

Shadow evaluation only: does not set achieved, scores, or final grades.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, TypedDict

RUBRIC_SUFFICIENCY_VERSION = "1.0"
SHADOW_MODE = "observation_only"

_EXECUTION_TIER_RANK = {"strong": 3, "medium": 2, "weak": 1, "unknown": 0}


class EvidenceClause(TypedDict, total=False):
    evidence_type: str
    system: str
    min_confidence: float
    min_count: int
    execution_evidence: List[str]


class SupportingEvidenceClause(TypedDict, total=False):
    evidence_type: str
    system: str
    min_count: int


class DisallowedEvidenceClause(TypedDict, total=False):
    evidence_type: str
    system: str
    noise_flag: str
    noise_detail_contains: str
    alone_insufficient: bool


class CriterionEvidenceContract(TypedDict, total=False):
    contract_id: str
    criterion: str
    aliases: List[str]
    required_evidence: List[EvidenceClause]
    supporting_evidence: List[SupportingEvidenceClause]
    disallowed_evidence: List[DisallowedEvidenceClause]
    minimum_modalities: int
    minimum_diversity: float
    minimum_confidence: float
    required_pass_ratio: float


def normalize_criterion_code(level: str) -> str:
    """A.P3 → P3, b.m1 → M1."""
    s = (level or "").strip().upper()
    if "." in s:
        s = s.split(".")[-1]
    return s


def _criterion_matches(level: str, contract: CriterionEvidenceContract) -> bool:
    norm = normalize_criterion_code(level)
    if not norm:
        return False
    primary = normalize_criterion_code(str(contract.get("criterion") or ""))
    if norm == primary:
        return True
    for alias in contract.get("aliases") or []:
        if normalize_criterion_code(str(alias)) == norm:
            return True
    return False


def _confidence_ok(value: Any, minimum: float) -> bool:
    try:
        return float(value) >= minimum
    except (TypeError, ValueError):
        return minimum <= 0.0


def _execution_ok(tier: Any, allowed: Optional[Sequence[str]]) -> bool:
    if not allowed:
        return True
    t = str(tier or "unknown").lower()
    return t in {str(x).lower() for x in allowed}


def _match_items(
    items: List[Dict[str, Any]],
    clause: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    et = clause.get("evidence_type")
    sysn = clause.get("system")
    out: List[Dict[str, Any]] = []
    for it in items:
        if et and it.get("evidence_type") != et:
            continue
        if sysn and it.get("system") != sysn:
            continue
        out.append(it)
    return out


def _best_item(matches: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not matches:
        return None

    def _score(it: Dict[str, Any]) -> tuple:
        try:
            conf = float(it.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        ev = str(it.get("execution_evidence") or "unknown").lower()
        return (conf, _EXECUTION_TIER_RANK.get(ev, 0))

    return max(matches, key=_score)


def _evaluate_required_clause(
    items: List[Dict[str, Any]],
    clause: EvidenceClause,
) -> Dict[str, Any]:
    matches = _match_items(items, clause)
    min_count = max(1, int(clause.get("min_count") or 1))
    min_conf = float(clause.get("min_confidence") or 0.0)
    allowed_exec = clause.get("execution_evidence")

    passing: List[Dict[str, Any]] = []
    for it in matches:
        if not _confidence_ok(it.get("confidence"), min_conf):
            continue
        if not _execution_ok(it.get("execution_evidence"), allowed_exec):
            continue
        passing.append(it)

    best = _best_item(matches)
    passed = len(passing) >= min_count
    missing_token = (
        f"missing_required:{clause.get('evidence_type') or 'any'}"
        + (f":{clause.get('system')}" if clause.get("system") else "")
    )

    return {
        "clause": dict(clause),
        "matched_count": len(matches),
        "passing_count": len(passing),
        "min_count": min_count,
        "passed": passed,
        "best_match": {
            "evidence_type": best.get("evidence_type") if best else None,
            "system": best.get("system") if best else None,
            "confidence": best.get("confidence") if best else None,
            "execution_evidence": best.get("execution_evidence") if best else None,
        }
        if best
        else None,
        "missing_token": missing_token if not passed else None,
    }


def _collect_noise_flags(evidence_layer: Mapping[str, Any]) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []
    cm = evidence_layer.get("cross_modal_corroboration") or {}
    for row in cm.get("cross_modal_noise_flags") or []:
        if isinstance(row, dict):
            flags.append(row)
    rc = evidence_layer.get("runtime_corroboration") or {}
    for row in rc.get("missing_runtime_corroboration_flags") or []:
        if isinstance(row, dict):
            flags.append(row)
    pt = evidence_layer.get("packet_tracer_evidence") or {}
    for row in pt.get("noise_flags") or []:
        if isinstance(row, dict):
            flags.append(row)
    xl = evidence_layer.get("excel_semantic_evidence") or {}
    summary = xl.get("spreadsheet_semantic_summary") or {}
    for row in summary.get("spreadsheet_noise_flags") or []:
        if isinstance(row, dict):
            flags.append(row)
    return flags


def _noise_flag_present(
    flags: List[Dict[str, Any]],
    noise_flag: str,
    detail_contains: Optional[str] = None,
) -> bool:
    for row in flags:
        if str(row.get("flag") or "") != noise_flag:
            continue
        if detail_contains:
            detail = str(row.get("detail") or "").lower()
            if detail_contains.lower() not in detail:
                continue
        return True
    return False


def _target_system(contract: CriterionEvidenceContract) -> Optional[str]:
    for clause in contract.get("required_evidence") or []:
        if clause.get("system"):
            return str(clause["system"])
    for clause in contract.get("supporting_evidence") or []:
        if clause.get("system"):
            return str(clause["system"])
    return None


def _modality_count_for_system(
    evidence_layer: Mapping[str, Any],
    system: Optional[str],
) -> int:
    rc = evidence_layer.get("runtime_corroboration") or {}
    by_sys = rc.get("by_system") or {}
    if system and isinstance(by_sys.get(system), dict):
        mods = (by_sys[system] or {}).get("corroboration_modalities") or []
        return len([m for m in mods if m])
    runtime_types = {
        "runtime_log",
        "runtime_screenshot",
        "video_frame",
        "ocr_text",
    }
    items = evidence_layer.get("items") or []
    present = {
        it.get("evidence_type")
        for it in items
        if isinstance(it, dict) and it.get("evidence_type") in runtime_types
    }
    if "code_system" in {
        it.get("evidence_type") for it in items if isinstance(it, dict)
    }:
        present.add("code_system")
    return len(present)


def _cross_modal_diversity(evidence_layer: Mapping[str, Any]) -> float:
    cm = evidence_layer.get("cross_modal_corroboration") or {}
    try:
        return float(cm.get("cross_modal_diversity_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _max_required_confidence(required_details: List[Dict[str, Any]]) -> float:
    best = 0.0
    for det in required_details:
        bm = det.get("best_match") or {}
        try:
            best = max(best, float(bm.get("confidence") or 0.0))
        except (TypeError, ValueError):
            continue
    return best


def _evaluate_disallowed(
    items: List[Dict[str, Any]],
    flags: List[Dict[str, Any]],
    contract: CriterionEvidenceContract,
    required_passed: bool,
    target_system: Optional[str],
) -> tuple[List[Dict[str, Any]], List[str]]:
    rejected: List[Dict[str, Any]] = []
    reasoning: List[str] = []
    insufficiency: List[Dict[str, str]] = []

    code_items = [it for it in items if it.get("evidence_type") == "code_system"]
    pattern_items = [it for it in items if it.get("evidence_type") == "pattern_hint"]
    runtime_logs = [it for it in items if it.get("evidence_type") == "runtime_log"]

    for clause in contract.get("disallowed_evidence") or []:
        et = clause.get("evidence_type")
        nf = clause.get("noise_flag")
        detail = clause.get("noise_detail_contains")
        alone = bool(clause.get("alone_insufficient"))

        if nf and _noise_flag_present(flags, str(nf), detail):
            rejected.append({"clause": dict(clause), "reason": f"noise_flag:{nf}"})
            reasoning.append(f"disallowed_noise_flag_{nf}")
            if "video_only" in str(nf) or (detail and "video_only" in detail):
                insufficiency.append({"flag": "video_only_windows_used_as_primary"})

        if et == "pattern_hint" and alone:
            has_code = any(
                it.get("evidence_type") == "code_system"
                and (not target_system or it.get("system") == target_system)
                for it in items
            )
            if pattern_items and not has_code and not required_passed:
                rejected.append({"clause": dict(clause), "reason": "pattern_hint_only"})
                reasoning.append("pattern_hints_only_without_code_system")
                insufficiency.append({"flag": "pattern_hints_only_insufficient"})

        if et == "pattern_hint" and not alone and pattern_items and not code_items:
            rejected.append({"clause": dict(clause), "reason": "pattern_without_code"})
            insufficiency.append({"flag": "pattern_hints_without_semantic_code"})

    if runtime_logs and target_system:
        has_system_code = any(
            it.get("evidence_type") == "code_system" and it.get("system") == target_system
            for it in items
        )
        if not has_system_code:
            insufficiency.append({"flag": "runtime_present_without_system_confirmation"})
            reasoning.append("runtime_log_present_without_matching_code_system")

    return rejected, reasoning, insufficiency


def _evaluate_supporting(
    items: List[Dict[str, Any]],
    contract: CriterionEvidenceContract,
) -> tuple[int, List[Dict[str, Any]], List[str]]:
    satisfied: List[Dict[str, Any]] = []
    reasoning: List[str] = []
    for clause in contract.get("supporting_evidence") or []:
        matches = _match_items(items, clause)
        min_count = max(1, int(clause.get("min_count") or 1))
        ok = len(matches) >= min_count
        row = {"clause": dict(clause), "matched_count": len(matches), "passed": ok}
        satisfied.append(row)
        if ok:
            et = clause.get("evidence_type") or "support"
            reasoning.append(f"supporting_{et}_present")
    count = sum(1 for s in satisfied if s.get("passed"))
    return count, satisfied, reasoning


def evaluate_criterion_sufficiency(
    evidence_layer: Optional[Mapping[str, Any]],
    contract: CriterionEvidenceContract,
    *,
    profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministic sufficiency evaluation for one contract (shadow / calibration).
    """
    layer: Dict[str, Any] = dict(evidence_layer or {})
    if profile and "runtime_corroboration" not in layer:
        from .runtime_corroboration import build_runtime_corroboration

        layer["runtime_corroboration"] = build_runtime_corroboration(profile)

    items = [it for it in (layer.get("items") or []) if isinstance(it, dict)]
    flags = _collect_noise_flags(layer)
    target_system = _target_system(contract)

    required_details: List[Dict[str, Any]] = []
    missing: List[str] = []
    req_reasoning: List[str] = []

    for clause in contract.get("required_evidence") or []:
        det = _evaluate_required_clause(items, clause)
        required_details.append(det)
        if det.get("passed"):
            et = clause.get("evidence_type") or "evidence"
            sys_part = f"_{clause['system']}" if clause.get("system") else ""
            req_reasoning.append(f"required_{et}{sys_part}_satisfied")
        else:
            tok = det.get("missing_token")
            if tok:
                missing.append(str(tok))

    n_req = len(required_details)
    n_pass = sum(1 for d in required_details if d.get("passed"))
    ratio = (n_pass / n_req) if n_req else 1.0
    threshold = max(0.0, min(1.0, float(contract.get("required_pass_ratio") or 1.0)))
    required_evidence_satisfied = ratio + 1e-9 >= threshold

    supporting_count, supporting_details, sup_reasoning = _evaluate_supporting(items, contract)

    rejected, dis_reasoning, insufficiency = _evaluate_disallowed(
        items, flags, contract, required_evidence_satisfied, target_system
    )

    # Runtime-only without code (explicit case b)
    if target_system:
        has_code = any(
            it.get("evidence_type") == "code_system" and it.get("system") == target_system
            for it in items
        )
        has_runtime = any(it.get("evidence_type") == "runtime_log" for it in items)
        if has_runtime and not has_code:
            if not any(x.get("flag") == "runtime_present_without_system_confirmation" for x in insufficiency):
                insufficiency.append({"flag": "runtime_present_without_system_confirmation"})
            dis_reasoning.append("runtime_present_without_system_confirmation")

    # OCR/video without corroboration (case d)
    rc = layer.get("runtime_corroboration") or {}
    cm = layer.get("cross_modal_corroboration") or {}
    ocr_or_video = any(
        it.get("evidence_type") in ("ocr_text", "video_frame") for it in items
    )
    has_code = any(it.get("evidence_type") == "code_system" for it in items)
    diversity = _cross_modal_diversity(layer)
    min_div = float(contract.get("minimum_diversity") or 0.0)
    if ocr_or_video and not has_code and diversity < min_div:
        insufficiency.append({"flag": "ocr_video_without_corroboration"})
        dis_reasoning.append("ocr_or_video_without_corroboration")

    if _noise_flag_present(
        flags,
        "video_frames_present_without_temporal_overlap",
        "video_only_windows",
    ):
        rejected.append(
            {
                "clause": {"noise_flag": "video_frames_present_without_temporal_overlap"},
                "reason": "video_only_windows",
            }
        )
        dis_reasoning.append("video_only_windows_not_used_as_sufficient")

    # Conflicting evidence (case e)
    conflicts = list(rc.get("corroboration_conflicts") or [])
    if conflicts:
        insufficiency.append({"flag": "corroboration_conflict_detected"})
        dis_reasoning.append("corroboration_conflicts_present")
        for c in conflicts[:5]:
            if isinstance(c, dict):
                rejected.append({"clause": c, "reason": str(c.get("flag") or "conflict")})

    modality_count = _modality_count_for_system(layer, target_system)
    min_modalities = int(contract.get("minimum_modalities") or 0)
    modalities_ok = modality_count >= min_modalities

    max_conf = _max_required_confidence(required_details)
    min_conf = float(contract.get("minimum_confidence") or 0.0)
    confidence_ok = max_conf + 1e-9 >= min_conf or (not contract.get("required_evidence"))

    diversity_ok = diversity + 1e-9 >= min_div

    if not modalities_ok:
        missing.append(f"insufficient_modalities:{modality_count}<{min_modalities}")
        insufficiency.append({"flag": "insufficient_modality_diversity"})
    if not diversity_ok and min_div > 0:
        missing.append(f"insufficient_cross_modal_diversity:{diversity}<{min_div}")
    if not confidence_ok:
        missing.append(f"insufficient_confidence:{max_conf}<{min_conf}")
        insufficiency.append({"flag": "required_confidence_not_met"})

    _blocking_flags = {
        "pattern_hints_only_insufficient",
        "runtime_present_without_system_confirmation",
        "ocr_video_without_corroboration",
        "corroboration_conflict_detected",
        "insufficient_modality_diversity",
        "required_confidence_not_met",
        "video_only_windows_used_as_primary",
    }
    has_blocking = any(x.get("flag") in _blocking_flags for x in insufficiency)

    sufficient = (
        required_evidence_satisfied
        and modalities_ok
        and diversity_ok
        and confidence_ok
        and not has_blocking
        and not missing
    )

    reasoning = sorted(
        set(
            req_reasoning
            + sup_reasoning
            + dis_reasoning
            + ([f"modalities_met:{modality_count}"] if modalities_ok else [])
            + ([f"cross_modal_diversity_met:{diversity}"] if diversity_ok else [])
            + (["required_evidence_satisfied"] if required_evidence_satisfied else [])
        )
    )

    sufficiency_result = {
        "criterion": contract.get("criterion"),
        "contract_id": contract.get("contract_id"),
        "sufficient": sufficient,
        "required_evidence_satisfied": required_evidence_satisfied,
        "required_pass_ratio": round(ratio, 4),
        "required_pass_threshold": threshold,
        "supporting_evidence_count": supporting_count,
        "missing_evidence": missing,
        "rejected_evidence": rejected,
        "modality_count": modality_count,
        "cross_modal_diversity_score": diversity,
    }

    seen_flags: Set[str] = set()
    deduped_insuff: List[Dict[str, str]] = []
    for row in insufficiency:
        f = row.get("flag")
        if not f or f in seen_flags:
            continue
        seen_flags.add(f)
        deduped_insuff.append({"flag": f})

    return {
        "rubric_sufficiency_version": RUBRIC_SUFFICIENCY_VERSION,
        "shadow_mode": SHADOW_MODE,
        "criterion": contract.get("criterion"),
        "contract_id": contract.get("contract_id"),
        "sufficiency_result": sufficiency_result,
        "sufficiency_reasoning": {"reasoning": reasoning},
        "insufficiency_flags": sorted(deduped_insuff, key=lambda x: x["flag"]),
        "required_details": required_details,
        "supporting_details": supporting_details,
        "limitations_ar": (
            "تقييم كفاية الأدلة حتمي وظلّي (observation_only)؛ لا يغيّر achieved أو الدرجة."
        ),
    }


def contract_game_collision_p3() -> CriterionEvidenceContract:
    """Default game-dev P3 collision contract (calibration + shadow)."""
    return {
        "contract_id": "game_collision_p3",
        "criterion": "P3",
        "aliases": ["A.P3", "P3", "a.p3"],
        "required_evidence": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "min_confidence": 0.7,
                "min_count": 1,
                "execution_evidence": ["medium", "strong"],
            }
        ],
        "supporting_evidence": [
            {"evidence_type": "runtime_log", "system": "collision_system", "min_count": 1},
            {"evidence_type": "runtime_screenshot", "min_count": 1},
            {"evidence_type": "video_frame", "min_count": 1},
            {"evidence_type": "ocr_text", "min_count": 1},
        ],
        "disallowed_evidence": [
            {"evidence_type": "pattern_hint", "alone_insufficient": True},
            {
                "noise_flag": "video_frames_present_without_temporal_overlap",
                "noise_detail_contains": "video_only_windows",
            },
        ],
        "minimum_modalities": 2,
        "minimum_diversity": 0.4,
        "minimum_confidence": 0.5,
        "required_pass_ratio": 1.0,
    }


def get_contract_registry() -> Dict[str, CriterionEvidenceContract]:
    c = contract_game_collision_p3()
    return {str(c["contract_id"]): c}


def resolve_contract_for_criterion(
    criteria_level: str,
    registry: Optional[Mapping[str, CriterionEvidenceContract]] = None,
) -> Optional[CriterionEvidenceContract]:
    reg = dict(registry or get_contract_registry())
    for contract in reg.values():
        if _criterion_matches(criteria_level, contract):
            return contract
    return None


def build_rubric_shadow_result(
    criteria_level: str,
    evidence_layer: Optional[Mapping[str, Any]],
    *,
    profile: Optional[Mapping[str, Any]] = None,
    contract: Optional[CriterionEvidenceContract] = None,
) -> Dict[str, Any]:
    """Shadow sufficiency package for one criterion level."""
    resolved = contract or resolve_contract_for_criterion(criteria_level)
    if not resolved:
        return {
            "shadow_mode": SHADOW_MODE,
            "criterion": normalize_criterion_code(criteria_level),
            "contract_id": None,
            "sufficiency_result": {
                "criterion": criteria_level,
                "sufficient": None,
                "required_evidence_satisfied": None,
                "supporting_evidence_count": 0,
                "missing_evidence": ["no_contract_registered"],
                "rejected_evidence": [],
            },
            "sufficiency_reasoning": {"reasoning": ["no_contract_registered"]},
            "insufficiency_flags": [{"flag": "no_rubric_contract"}],
        }
    out = evaluate_criterion_sufficiency(evidence_layer, resolved, profile=profile)
    out["criteria_level"] = criteria_level
    return out


def attach_rubric_sufficiency_shadow(
    grading_result: Dict[str, Any],
    evidence_layer: Mapping[str, Any],
    *,
    profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Attach rubric_shadow_result to each criteria_result academic_snapshot.
    Does not modify achieved. Returns layer-level shadow summary.
    """
    layer_shadow: Dict[str, Any] = {
        "version": RUBRIC_SUFFICIENCY_VERSION,
        "shadow_mode": SHADOW_MODE,
        "by_criterion": {},
    }

    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        lvl = str(cr.get("criteria_level") or "")
        shadow = build_rubric_shadow_result(lvl, evidence_layer, profile=profile)
        layer_shadow["by_criterion"][lvl] = {
            "contract_id": shadow.get("contract_id"),
            "sufficient": (shadow.get("sufficiency_result") or {}).get("sufficient"),
            "insufficiency_flags": shadow.get("insufficiency_flags") or [],
        }
        snap = cr.get("academic_snapshot")
        if not isinstance(snap, dict):
            snap = {}
            cr["academic_snapshot"] = snap
        snap["rubric_shadow_result"] = shadow

    return layer_shadow


def build_evidence_layer_rubric_shadow(
    evidence_layer: Mapping[str, Any],
    criteria_levels: Sequence[str],
    *,
    profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer-level rubric shadow block (no grading_result required)."""
    by_crit: Dict[str, Any] = {}
    for lvl in criteria_levels:
        if not lvl:
            continue
        by_crit[str(lvl)] = build_rubric_shadow_result(
            str(lvl), evidence_layer, profile=profile
        )
    return {
        "version": RUBRIC_SUFFICIENCY_VERSION,
        "shadow_mode": SHADOW_MODE,
        "by_criterion": by_crit,
    }
