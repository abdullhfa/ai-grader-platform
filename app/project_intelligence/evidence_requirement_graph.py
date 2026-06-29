"""
Evidence Requirement Graph — declarative sufficiency model for BTEC-style criteria.

Not a chain of ad-hoc IFs: criteria reference typed evidence rules + thresholds.
Use with evidence_layer (evidence_schema) from grading_snapshot.

Calibration / rubric packs can load CriterionEvidenceSpec from DB or JSON later.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

GRAPH_SCHEMA_VERSION = "0.1"

ExecutionTier = Literal["weak", "medium", "strong", "unknown"]


class RequiredEvidenceRule(TypedDict, total=False):
    """One mandatory evidence clause for a criterion."""

    type: str  # e.g. "code_system"
    system: str  # e.g. "collision_system"
    min_confidence: float  # e.g. 0.7
    execution: List[str]  # e.g. ["medium", "strong"] — tier names


class CriterionEvidenceSpec(TypedDict, total=False):
    """
    Declarative spec: what counts as sufficient evidence for one criterion code
    (e.g. "A.P3" or "P3").
    """

    criterion: str
    required_evidence: List[RequiredEvidenceRule]
    supporting_evidence: List[str]  # reserved: video, test logs, etc.
    threshold: float  # 0–1: min fraction of required rules that must pass


def _execution_ok(
    tier: Optional[str],
    allowed: Optional[List[str]],
) -> bool:
    if not allowed:
        return True
    t = (tier or "unknown").lower()
    return t in {x.lower() for x in allowed}


def _confidence_ok(conf: Any, minimum: float) -> bool:
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return False
    return c >= minimum


def _find_matching_items(
    items: List[Dict[str, Any]],
    rule: RequiredEvidenceRule,
) -> List[Dict[str, Any]]:
    et = rule.get("type")
    sysn = rule.get("system")
    out: List[Dict[str, Any]] = []
    for it in items:
        if et and it.get("evidence_type") != et:
            continue
        if sysn and it.get("system") != sysn:
            continue
        out.append(it)
    return out


def evaluate_criterion_evidence_sufficiency(
    evidence_layer: Optional[Dict[str, Any]],
    spec: CriterionEvidenceSpec,
) -> Dict[str, Any]:
    """
    Deterministic sufficiency check. Does not call any LLM.

    Returns:
      satisfied: all required rules pass (after threshold on pass ratio if < 1 rule, threshold still applies)
      rules_evaluated, rules_passed, details
    """
    items: List[Dict[str, Any]] = list((evidence_layer or {}).get("items") or [])
    required = list(spec.get("required_evidence") or [])
    threshold = float(spec.get("threshold") or 1.0)
    threshold = max(0.0, min(1.0, threshold))

    details: List[Dict[str, Any]] = []
    passed = 0
    for rule in required:
        matches = _find_matching_items(items, rule)
        best = None
        ok = False
        if matches:
            # Take strongest: max confidence, then execution tier order
            tier_rank = {"strong": 3, "medium": 2, "weak": 1, "unknown": 0}

            def score(it: Dict[str, Any]) -> tuple:
                conf = float(it.get("confidence") or 0.0)
                ev = str(it.get("execution_evidence") or "unknown").lower()
                return (conf, tier_rank.get(ev, 0))

            best = max(matches, key=score)
            min_c = float(rule.get("min_confidence") or 0.0)
            ok = _confidence_ok(best.get("confidence"), min_c) and _execution_ok(
                str(best.get("execution_evidence")),
                rule.get("execution"),
            )
        details.append(
            {
                "rule": dict(rule),
                "matched": bool(matches),
                "best_match": {
                    "system": best.get("system"),
                    "confidence": best.get("confidence"),
                    "execution_evidence": best.get("execution_evidence"),
                }
                if best
                else None,
                "passed": ok,
            }
        )
        if ok:
            passed += 1

    n = len(required)
    if n == 0:
        ratio = 1.0
        satisfied = True
    else:
        ratio = passed / n
        # threshold = min fraction of required rules that must pass (Evidence Sufficiency Model)
        satisfied = ratio + 1e-9 >= threshold

    return {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "criterion": spec.get("criterion"),
        "satisfied": satisfied,
        "pass_ratio": round(ratio, 4),
        "threshold": threshold,
        "rules_required": n,
        "rules_passed": passed,
        "details": details,
        "supporting_evidence_requested": list(spec.get("supporting_evidence") or []),
    }


def example_spec_collision_p3() -> CriterionEvidenceSpec:
    """Illustrative graph fragment (replace with assignment-specific rubric pack)."""
    return {
        "criterion": "P3",
        "required_evidence": [
            {
                "type": "code_system",
                "system": "collision_system",
                "min_confidence": 0.7,
                "execution": ["medium", "strong"],
            }
        ],
        "supporting_evidence": ["testing_evidence", "gameplay_video"],
        "threshold": 1.0,
    }
