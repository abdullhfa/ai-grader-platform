"""
Replay Cohort Registry — declarative cohort definitions for disparity analysis.

Cohort semantics evolve via definition_contract versions.
Read-only definitions — used by replay_disparity_analytics only.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

COHORT_DEFINITION_CONTRACT = "cohort_v1"

# Signal evaluators receive (snap, replay_state, procedural_path, evidence_profiles)
SignalFn = Callable[
    [Dict[str, Any], Dict[str, Any], Dict[str, Any], List[str]],
    bool,
]


def _has_executable(snap: Dict[str, Any]) -> bool:
    inv = snap.get("artifact_inventory") or {}
    exe = inv.get("executable_artifacts") or {}
    rt = inv.get("runtime_artifacts") or {}
    return bool(exe.get("files") or rt.get("executables_detected"))


def _has_word_pdf(snap: Dict[str, Any]) -> bool:
    doc = (snap.get("artifact_inventory") or {}).get("documentation") or {}
    return any(
        str(f.get("ext") or "").lower() in (".docx", ".doc", ".pdf", ".odt")
        for f in doc.get("files") or []
    )


def _weak_extraction(snap: Dict[str, Any]) -> bool:
    expl = snap.get("explainability_layer") or {}
    inv = snap.get("artifact_inventory") or {}
    cov = expl.get("extraction_coverage") or inv.get("extraction_coverage") or {}
    if cov.get("weak_analysis_risk"):
        return True
    ratio = cov.get("coverage_ratio")
    return ratio is not None and float(ratio) < 0.5


def _has_playtest(snap: Dict[str, Any], state: Dict[str, Any]) -> bool:
    l5 = (snap.get("artifact_inventory") or {}).get("l5_human_playtest") or {}
    if l5.get("pass"):
        return True
    return bool(state.get("playtest_completed"))


def _documentation_rich(snap: Dict[str, Any]) -> bool:
    inv = snap.get("artifact_inventory") or {}
    doc = inv.get("documentation") or {}
    testing = inv.get("testing_evidence") or {}
    emb = inv.get("embedded_screenshots") or {}
    has_word = _has_word_pdf(snap)
    has_testing = bool(testing.get("files"))
    has_shots = (emb.get("count") or 0) > 0
    return has_word and (has_testing or has_shots)


SIGNAL_EVALUATORS: Dict[str, SignalFn] = {
    "runtime_present": lambda snap, state, path, profiles: _has_executable(snap),
    "documentation_missing": lambda snap, state, path, profiles: not _has_word_pdf(snap),
    "weak_extraction": lambda snap, state, path, profiles: _weak_extraction(snap),
    "documentation_present": lambda snap, state, path, profiles: _has_word_pdf(snap),
    "documentation_rich": lambda snap, state, path, profiles: _documentation_rich(snap),
    "human_playtest_present": lambda snap, state, path, profiles: _has_playtest(snap, state),
    "synthetic_reconstruction": lambda snap, state, path, profiles: bool(
        path.get("replay_source_synthetic")
    ),
    "partial_code_extraction": lambda snap, state, path, profiles: "partial_code_extraction"
    in profiles,
    "runtime_only_profile": lambda snap, state, path, profiles: "runtime_only" in profiles,
}


COHORT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "runtime_only": {
        "cohort_id": "runtime_only",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Runtime-only cohort",
        "label_en": "Runtime-only (exe-led, minimal doc/code)",
        "criteria": ["runtime_present", "documentation_missing"],
        "criteria_logic": "all",
    },
    "partial_code_extraction": {
        "cohort_id": "partial_code_extraction",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Partial code extraction cohort",
        "label_en": "Partial code extraction",
        "criteria": ["weak_extraction"],
        "criteria_logic": "all",
    },
    "documentation_rich": {
        "cohort_id": "documentation_rich",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Documentation-rich cohort",
        "label_en": "Documentation-rich",
        "criteria": ["documentation_rich"],
        "criteria_logic": "all",
    },
    "word_pdf": {
        "cohort_id": "word_pdf",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Word/PDF cohort",
        "label_en": "Word/PDF documentation",
        "criteria": ["documentation_present"],
        "criteria_logic": "all",
    },
    "human_playtest_present": {
        "cohort_id": "human_playtest_present",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Human playtest cohort",
        "label_en": "Manual Playtest L5 present",
        "criteria": ["human_playtest_present"],
        "criteria_logic": "all",
    },
    "synthetic_reconstruction": {
        "cohort_id": "synthetic_reconstruction",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Synthetic reconstruction cohort",
        "label_en": "Synthetic event log reconstruction",
        "criteria": ["synthetic_reconstruction"],
        "criteria_logic": "all",
    },
}

# Composite zones — intersection of base cohorts (both must match on same submission)
COMPOSITE_COHORT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "zone_id": "runtime_only+partial_code_extraction",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Runtime-only + weak extraction",
        "required_cohorts": ["runtime_only", "partial_code_extraction"],
    },
    {
        "zone_id": "runtime_only+synthetic_reconstruction",
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "label_ar": "Runtime-only + synthetic reconstruction",
        "required_cohorts": ["runtime_only", "synthetic_reconstruction"],
    },
]


def evaluate_submission_signals(
    snap: Dict[str, Any],
    *,
    replay_state: Optional[Dict[str, Any]] = None,
    procedural_path: Optional[Dict[str, Any]] = None,
    evidence_profiles: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """Evaluate all registry signals for one submission."""
    state = replay_state or {}
    path = procedural_path or {}
    profiles = evidence_profiles or []
    return {name: fn(snap, state, path, profiles) for name, fn in SIGNAL_EVALUATORS.items()}


def _cohort_matches(definition: Dict[str, Any], signals: Dict[str, bool]) -> bool:
    criteria = definition.get("criteria") or []
    if not criteria:
        return False
    logic = definition.get("criteria_logic") or "all"
    results = [signals.get(c, False) for c in criteria]
    if logic == "any":
        return any(results)
    return all(results)


def classify_replay_cohorts(
    snap: Dict[str, Any],
    *,
    replay_state: Optional[Dict[str, Any]] = None,
    procedural_path: Optional[Dict[str, Any]] = None,
    evidence_profiles: Optional[List[str]] = None,
) -> List[str]:
    """Assign cohort memberships via registry — replay-context aware."""
    signals = evaluate_submission_signals(
        snap,
        replay_state=replay_state,
        procedural_path=procedural_path,
        evidence_profiles=evidence_profiles,
    )
    matched: List[str] = []
    for cohort_id, definition in COHORT_REGISTRY.items():
        if _cohort_matches(definition, signals):
            matched.append(cohort_id)
    return sorted(matched) if matched else ["unclassified"]


def classify_composite_zones(matched_cohorts: List[str]) -> List[str]:
    """Composite zone IDs when all required cohorts present on same submission."""
    cohort_set: Set[str] = set(matched_cohorts)
    zones: List[str] = []
    for comp in COMPOSITE_COHORT_DEFINITIONS:
        required = set(comp.get("required_cohorts") or [])
        if required and required.issubset(cohort_set):
            zones.append(str(comp["zone_id"]))
    return sorted(zones)


def get_cohort_label(cohort_id: str) -> str:
    if cohort_id in COHORT_REGISTRY:
        return str(COHORT_REGISTRY[cohort_id].get("label_ar") or cohort_id)
    for comp in COMPOSITE_COHORT_DEFINITIONS:
        if comp.get("zone_id") == cohort_id:
            return str(comp.get("label_ar") or cohort_id)
    return cohort_id


def list_cohort_registry() -> Dict[str, Any]:
    """Export registry for API / institutional reporting."""
    return {
        "definition_contract": COHORT_DEFINITION_CONTRACT,
        "cohorts": [dict(v) for v in COHORT_REGISTRY.values()],
        "composite_zones": list(COMPOSITE_COHORT_DEFINITIONS),
        "signals_available": sorted(SIGNAL_EVALUATORS.keys()),
        "note_ar": "تعريفات cohort — declarative — تتطور عبر definition_contract",
    }
