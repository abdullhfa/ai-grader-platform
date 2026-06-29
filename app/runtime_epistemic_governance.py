"""
Runtime epistemic governance — three layers, never auto-merged.

Invariants:
  Governed runtime observation is still not runtime understanding.
  runtime governance ≠ runtime comprehension
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, FrozenSet, List, Optional

from app.runtime_observation_contract import get_l4_phenomenology_clause

SPEC_ID = "RUNTIME_EPISTEMIC_GOVERNANCE_v1"
QUARANTINE_SCHEMA_ID = "RUNTIME_QUARANTINE_STATES_v1"
L4_CLAUSE_ID = "RUNTIME_L4_PHENOMENOLOGY_CLAUSE_v1"

PRIMARY_INVARIANT_EN = "Governed runtime observation is still not runtime understanding."
GOVERNANCE_COMPREHENSION_EN = "runtime governance ≠ runtime comprehension"
EXECUTION_OPACITY_EN = (
    "Even with dense telemetry, gameplay · pedagogical · rubric-wise meaning "
    "remain partially opaque."
)
OVERCONFIDENCE_RISK_EN = "phenomenological overconfidence"

RUNTIME_QUARANTINE_STATES: FrozenSet[str] = frozenset({
    "runtime_observed",
    "runtime_continuous",
    "runtime_reproducible",
    "runtime_provenance_partial",
    "runtime_epistemically_unverified",
    "runtime_legitimacy_blocked",
})

MANDATORY_QUARANTINE_STATES: FrozenSet[str] = frozenset({
    "runtime_epistemically_unverified",
    "runtime_legitimacy_blocked",
})

LAYER_IDS = ("runtime_phenomenology", "provenance_governance", "legitimacy_governance")


def build_phenomenology_governance_layer(
    wiring_bundle: Optional[Dict[str, Any]] = None,
    *,
    execution_phenomenology: Optional[Dict[str, Any]] = None,
    replay_phenomenology: Optional[Dict[str, Any]] = None,
    raw_telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer 1 — what appeared. No meaning, no legitimacy."""
    if wiring_bundle:
        execution_phenomenology = execution_phenomenology or wiring_bundle.get("execution_phenomenology")
        replay_phenomenology = replay_phenomenology or wiring_bundle.get("replay_phenomenology")
        raw_telemetry = raw_telemetry or wiring_bundle.get("raw_telemetry")
    trace_count = 0
    if raw_telemetry:
        trace_count = int(raw_telemetry.get("trace_count") or len(raw_telemetry.get("traces") or []))
    return {
        "layer_id": "runtime_phenomenology",
        "function_en": "what appeared",
        "assigns_meaning": False,
        "assigns_legitimacy": False,
        "assigns_comprehension": False,
        "execution_phenomenology": execution_phenomenology,
        "replay_phenomenology": replay_phenomenology,
        "raw_telemetry_trace_count": trace_count,
        "invariant_en": PRIMARY_INVARIANT_EN,
    }


def build_provenance_governance_layer(
    wiring_bundle: Optional[Dict[str, Any]] = None,
    *,
    provenance_segment: Optional[Dict[str, Any]] = None,
    provenance_chain: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Layer 2 — what can be linked. No authenticity, no legitimacy."""
    if wiring_bundle:
        provenance_segment = provenance_segment or wiring_bundle.get("provenance_chain_segment")
    chain = list(provenance_chain or [])
    if provenance_segment:
        chain = chain + [provenance_segment]
    identity_complete = bool(
        provenance_segment
        and provenance_segment.get("prior_segment_id")
        and provenance_segment.get("artifact_name")
    )
    return {
        "layer_id": "provenance_governance",
        "function_en": "what can be linked",
        "assigns_authenticity": False,
        "assigns_legitimacy": False,
        "provenance_chain_segments": chain,
        "identity_complete": identity_complete,
        "linkage_mode": "observation_only",
        "note_en": "Linkage observed — not validated.",
    }


def build_legitimacy_governance_layer(*, blocked: bool = True) -> Dict[str, Any]:
    """Layer 3 — blocked by default. Never auto-unlocked by layers 1–2."""
    return {
        "layer_id": "legitimacy_governance",
        "function_en": "blocked by default",
        "blocked": blocked,
        "default_state": "blocked",
        "unlock_requires": "human_governed_explicit_gate",
        "achievement_inference": False,
        "gameplay_legitimacy_inference": False,
        "l4_clause_en": get_l4_phenomenology_clause()["clause_en"],
    }


def classify_runtime_quarantine_states(
    wiring_bundle: Optional[Dict[str, Any]] = None,
    *,
    has_process_activity: bool = False,
    has_continuity: bool = False,
    has_replay_stable: bool = False,
    provenance_partial: bool = True,
) -> List[str]:
    """Derive runtime quarantine states from wiring — never collapse to legitimacy."""
    states: List[str] = []
    if wiring_bundle:
        raw = wiring_bundle.get("raw_telemetry") or {}
        traces = raw.get("traces") or []
        has_process_activity = has_process_activity or any(
            t.get("signal_type") == "process_lifecycle" for t in traces
        )
        has_continuity = has_continuity or any(
            t.get("signal_type") == "render_continuity" for t in traces
        )
        replay = wiring_bundle.get("replay_phenomenology") or {}
        replay_desc = set(replay.get("descriptors") or [])
        has_replay_stable = has_replay_stable or bool(
            replay_desc & {"replay_deterministic", "replay_reproducible", "replay_continuous"}
        )
        prov = wiring_bundle.get("provenance_chain_segment") or {}
        provenance_partial = provenance_partial or not prov.get("identity_complete", False)

    if has_process_activity:
        states.append("runtime_observed")
    if has_continuity:
        states.append("runtime_continuous")
    if has_replay_stable:
        states.append("runtime_reproducible")
    if provenance_partial:
        states.append("runtime_provenance_partial")
    states.append("runtime_epistemically_unverified")
    states.append("runtime_legitimacy_blocked")
    return states


def check_phenomenological_overconfidence(
    wiring_bundle: Optional[Dict[str, Any]] = None,
    *,
    trace_count: int = 0,
    quarantine_states: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Advisory — dense signals increase overconfidence risk without proving meaning."""
    if wiring_bundle:
        raw = wiring_bundle.get("raw_telemetry") or {}
        trace_count = int(raw.get("trace_count") or len(raw.get("traces") or []))
        quarantine_states = quarantine_states or classify_runtime_quarantine_states(wiring_bundle)
    density_high = trace_count >= 5
    has_repro = quarantine_states and "runtime_reproducible" in quarantine_states
    has_continuous = quarantine_states and "runtime_continuous" in quarantine_states
    risk = density_high or (has_repro and has_continuous)
    return {
        "risk_id": OVERCONFIDENCE_RISK_EN,
        "detected": risk,
        "trace_count": trace_count,
        "advisory_en": (
            "Dense traces and replay continuity may induce comprehension illusion. "
            "Epistemic meaning remains unverified."
        ),
        "mitigation_en": "execution opacity preservation · mandatory unverified + legitimacy_blocked states",
    }


def validate_no_layer_auto_merge(governance_bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure layers remain separate — no merged legitimacy claim."""
    violations: List[str] = []
    if governance_bundle.get("layers_merged"):
        violations.append("layers_merged flag must not be true")
    phen = governance_bundle.get("runtime_phenomenology") or {}
    prov = governance_bundle.get("provenance_governance") or {}
    leg = governance_bundle.get("legitimacy_governance") or {}
    if phen.get("assigns_legitimacy"):
        violations.append("phenomenology layer assigns legitimacy")
    if prov.get("assigns_legitimacy") or prov.get("assigns_authenticity"):
        violations.append("provenance layer assigns authenticity/legitimacy")
    if not leg.get("blocked", True):
        violations.append("legitimacy layer unblocked without explicit gate")
    merged_claim = governance_bundle.get("gameplay_understood") or governance_bundle.get("comprehension_granted")
    if merged_claim:
        violations.append("comprehension claim in governance bundle")
    return {"allowed": len(violations) == 0, "violations": violations}


def build_runtime_epistemic_governance_bundle(
    wiring_bundle: Optional[Dict[str, Any]] = None,
    *,
    provenance_chain: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Assemble three governance layers without auto-merge.
    Does NOT append to ledger.
    """
    phen_layer = build_phenomenology_governance_layer(wiring_bundle)
    prov_layer = build_provenance_governance_layer(wiring_bundle, provenance_chain=provenance_chain)
    leg_layer = build_legitimacy_governance_layer(blocked=True)
    quarantine_states = classify_runtime_quarantine_states(wiring_bundle)
    overconfidence = check_phenomenological_overconfidence(wiring_bundle, quarantine_states=quarantine_states)
    bundle = {
        "spec_id": SPEC_ID,
        "governance_id": f"reg_{uuid.uuid4().hex[:12]}",
        "assigns_authority": False,
        "assigns_legitimacy": False,
        "assigns_comprehension": False,
        "layers_merged": False,
        "auto_merge_forbidden": True,
        "invariants": {
            "governed_observation": PRIMARY_INVARIANT_EN,
            "governance_comprehension": GOVERNANCE_COMPREHENSION_EN,
            "execution_opacity": EXECUTION_OPACITY_EN,
        },
        "l4_clause_id": L4_CLAUSE_ID,
        "l4_clause": get_l4_phenomenology_clause(),
        "runtime_phenomenology": phen_layer,
        "provenance_governance": prov_layer,
        "legitimacy_governance": leg_layer,
        "runtime_quarantine_states": quarantine_states,
        "runtime_quarantine_mandatory_present": all(
            s in quarantine_states for s in MANDATORY_QUARANTINE_STATES
        ),
        "phenomenological_overconfidence_check": overconfidence,
        "execution_opacity_preservation": {
            "gameplay_internal_state": "partially_opaque",
            "pedagogical_meaning": "partially_opaque",
            "rubric_satisfaction": "partially_opaque",
            "note_en": EXECUTION_OPACITY_EN,
        },
        "source_wiring_id": (wiring_bundle or {}).get("wiring_id"),
    }
    merge_check = validate_no_layer_auto_merge(bundle)
    bundle["layer_separation_check"] = merge_check
    if not merge_check.get("allowed"):
        raise ValueError(
            "governance bundle violates layer separation: "
            + ", ".join(merge_check.get("violations") or [])
        )
    return bundle
