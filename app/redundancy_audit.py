"""
Redundancy audit — what exists because earlier uncertainty was unresolved?

Categories: invariant_critical | protective_redundancy | interpretive_surplus
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIT_ID = "REDUNDANCY_AUDIT_v1"
PHASE_ID = "ARCHITECTURAL_HARDENING_v1"
AUDIT_ARTIFACT = (
    Path(__file__).resolve().parent
    / "calibration"
    / "REDUNDANCY_AUDIT_v1.json"
)

AUDIT_QUESTION_EN = (
    "What currently exists only because earlier uncertainty was unresolved?"
)
HARDENING_INVARIANT_EN = "Constitutional protection must remain comprehensible."
PRESERVED_EN = "The system still refuses to certify itself — empty ledgers intentional."

CATEGORIES = (
    "invariant_critical",
    "protective_redundancy",
    "interpretive_surplus",
)


def load_audit() -> Dict[str, Any]:
    return json.loads(AUDIT_ARTIFACT.read_text(encoding="utf-8"))


def run_redundancy_audit() -> Dict[str, Any]:
    """Return full audit with live ledger discipline check."""
    audit = load_audit()
    ledger = (
        Path(__file__).resolve().parent
        / "calibration"
        / "human_cohort_workshop"
        / "runtime_observation_ledger.jsonl"
    )
    ledger_empty = not ledger.exists() or ledger.read_text(encoding="utf-8").strip() == ""
    by_category: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for entry in audit.get("entries") or []:
        cat = entry.get("category") or "interpretive_surplus"
        if cat in by_category:
            by_category[cat].append(entry)
    return {
        "audit_id": AUDIT_ID,
        "phase_id": PHASE_ID,
        "audit_question_en": AUDIT_QUESTION_EN,
        "hardening_invariant_en": HARDENING_INVARIANT_EN,
        "preserved_non_negotiable_en": PRESERVED_EN,
        "ledger_empty_confirmed": ledger_empty,
        "self_certification_refused": ledger_empty,
        "by_category": by_category,
        "summary": audit.get("summary") or {},
        "review_areas": audit.get("review_areas") or [],
        "forbidden_audit_actions": audit.get("forbidden_audit_actions") or [],
        "recommended_next_en": (
            "Execute merge actions on protective_redundancy only — "
            "no deletions on invariant_critical."
        ),
    }


def entries_by_action(action: str) -> List[Dict[str, Any]]:
    audit = load_audit()
    return [e for e in (audit.get("entries") or []) if e.get("action") == action]


def merge_candidates() -> List[Dict[str, Any]]:
    audit = load_audit()
    return [
        e for e in (audit.get("entries") or [])
        if e.get("category") == "protective_redundancy"
    ]


def pause_candidates() -> List[Dict[str, Any]]:
    audit = load_audit()
    return [
        e for e in (audit.get("entries") or [])
        if e.get("category") == "interpretive_surplus"
    ]


def invariant_critical_surfaces() -> List[Dict[str, Any]]:
    audit = load_audit()
    return [
        e for e in (audit.get("entries") or [])
        if e.get("category") == "invariant_critical"
    ]


def explanation_burden_check(
    *,
    merge_id: str,
    canonical_surfaces_before: int,
    canonical_surfaces_after: int,
    interpretive_power_increased: bool = False,
    legitimacy_surface_expanded: bool = False,
    abstraction_layer_added: bool = False,
) -> Dict[str, Any]:
    """
    Did the merge reduce explanation burden?
    Hardening passes only if surfaces shrink without added interpretive power.
    """
    reduced = canonical_surfaces_after < canonical_surfaces_before
    passed = (
        reduced
        and not interpretive_power_increased
        and not legitimacy_surface_expanded
        and not abstraction_layer_added
    )
    return {
        "merge_id": merge_id,
        "question_en": "Did the merge reduce explanation burden?",
        "canonical_surfaces_before": canonical_surfaces_before,
        "canonical_surfaces_after": canonical_surfaces_after,
        "explanation_burden_reduced": reduced,
        "interpretive_power_increased": interpretive_power_increased,
        "legitimacy_surface_expanded": legitimacy_surface_expanded,
        "abstraction_layer_added": abstraction_layer_added,
        "passed": passed,
        "principle_en": "Merge by compression, not abstraction.",
    }


def load_hardening_merge_log(merge_id: str = "HARDENING_MERGE_1") -> Dict[str, Any]:
    path = (
        Path(__file__).resolve().parent
        / "calibration"
        / "human_cohort_workshop"
        / f"{merge_id}.json"
    )
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def hardening_gate_for_reduction(
    *,
    touches_invariant_critical: bool,
    merges_protective_redundancy: bool,
    removes_interpretive_surplus: bool,
    preserves_empty_ledger: bool = True,
    preserves_comprehensibility: bool = True,
) -> Dict[str, Any]:
    """Gate any reduction action during hardening."""
    if touches_invariant_critical:
        return {
            "allowed": False,
            "reason_en": "Cannot modify invariant-critical surfaces during merge/pause.",
        }
    if not preserves_empty_ledger:
        return {
            "allowed": False,
            "reason_en": "Empty ledger discipline is non-negotiable.",
        }
    if not preserves_comprehensibility:
        return {
            "allowed": False,
            "reason_en": HARDENING_INVARIANT_EN,
        }
    allowed = merges_protective_redundancy or removes_interpretive_surplus
    return {
        "allowed": allowed,
        "reduction_without_epistemic_loss": allowed,
        "hardening_invariant_en": HARDENING_INVARIANT_EN,
    }
