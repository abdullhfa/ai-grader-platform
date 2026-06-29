"""
Counterfactual Governance Replay — isolated sandbox (analytical only).

Same events + different governance contract → counterfactual academic state.
Does NOT mutate snapshots, event log, or adjudications.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.deterministic_replay_engine import (
    compute_replayed_protected_digest,
    compute_replayed_state_hash,
    replay_events,
)
from app.evidence_lineage import CONFIDENCE_WEIGHTS
from app.governance_contract_registry import (
    DEFAULT_BASELINE_CONTRACT,
    DEFAULT_COMPARISON_CONTRACT,
    get_contract,
)

SANDBOX_MODE = "counterfactual_replay_sandbox"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _artifact_id() -> str:
    return f"drift_{uuid.uuid4().hex[:16]}"


def _estimate_execution_confidence(
    state: Dict[str, Any],
    criterion_key: str,
    *,
    sandbox_context: Optional[Dict[str, Any]] = None,
) -> float:
    """Best-effort confidence from replay state + optional read-only lineage context."""
    ctx = sandbox_context or {}
    lineage = ctx.get("evidence_lineage") or {}
    crit = (lineage.get("criteria") or {}).get(
        "C.P5" if criterion_key == "P5" else "C.P6"
    ) or {}
    node_ids = (crit.get("lineage") or {}).get("evidence_nodes") or []
    shared = lineage.get("shared_nodes") or {}
    confs = [
        float((shared.get(nid) or {}).get("confidence") or 0)
        for nid in node_ids
        if (shared.get(nid) or {}).get("type") != "governance_gate"
    ]
    if confs:
        return round(max(confs), 4)

    gov = state.get("governance") or {}
    playtest = state.get("playtest") or {}
    if playtest.get("completed") and playtest.get("pass"):
        return CONFIDENCE_WEIGHTS["human_playtest"]
    if gov.get("runtime_status") == "completed":
        return CONFIDENCE_WEIGHTS["runtime_observation"]
    if not gov.get("runtime_gated"):
        return CONFIDENCE_WEIGHTS["runtime_observation"] * 0.9
    return CONFIDENCE_WEIGHTS["exe_detected_only"]


def apply_counterfactual_contract(
    factual_state: Dict[str, Any],
    *,
    contract_id: str,
    events: Optional[List[Dict[str, Any]]] = None,
    sandbox_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Isolated overlay — re-interpret factual replay state under a governance contract.
    Pure function; returns new state dict.
    """
    contract = get_contract(contract_id)
    state = copy.deepcopy(factual_state)
    state["counterfactual"] = True
    state["governance_contract_applied"] = contract_id
    state["sandbox_mode"] = SANDBOX_MODE

    gov = state.setdefault("governance", {})
    ev_list = events or []

    has_runtime_observation = any(
        e.get("event_type") == "governance_state"
        and (e.get("payload") or {}).get("status") == "completed"
        for e in ev_list
    )
    has_exe_signal = any(
        e.get("event_type") in ("initial_grading", "runtime_gated")
        for e in ev_list
    )

    if contract.get("l4_sandbox_permitted") and not contract.get("runtime_gated_by_default"):
        if gov.get("runtime_gated") or has_exe_signal:
            gov["runtime_gated"] = False
            gov["runtime_status"] = "observation_permitted_counterfactual"
            if has_runtime_observation:
                gov["active_authority"] = "RUNTIME_OBSERVATION_L4"
            else:
                gov["active_authority"] = "RUNTIME_OBSERVATION_L4"
            state["replay_epoch"] = "COUNTERFACTUAL_L4_PERMITTED"
    elif contract.get("runtime_gated_by_default"):
        gov["runtime_gated"] = True
        gov["runtime_status"] = "gated"
        gov["active_authority"] = "SYSTEM_GOVERNED"

    min_conf = float(contract.get("min_confidence_achievement") or 0.93)
    require_l5 = bool(contract.get("human_playtest_required_for_execution_criteria"))
    playtest_ok = bool((state.get("playtest") or {}).get("completed"))

    for key in ("P5", "P6"):
        crit = state.get("criteria", {}).get(key)
        if not isinstance(crit, dict):
            continue

        conf = _estimate_execution_confidence(state, key, sandbox_context=sandbox_context)
        achieved = bool(crit.get("achieved"))
        status = str(crit.get("status") or ("ACHIEVED" if achieved else "NOT_ACHIEVED"))

        if require_l5 and not playtest_ok:
            if status != "ACHIEVED":
                status = "HOLD"
                achieved = False
                crit["achievement_authority"] = "SYSTEM_GOVERNED"
        elif conf >= min_conf and contract.get("l4_sandbox_permitted") and playtest_ok:
            status = "ACHIEVED"
            achieved = True
            crit["achievement_authority"] = "HUMAN_PLAYTEST_L5"
        elif conf >= min_conf and contract.get("l4_sandbox_permitted") and not require_l5:
            if has_runtime_observation or not gov.get("runtime_gated"):
                status = "ACHIEVED"
                achieved = True
                crit["achievement_authority"] = "RUNTIME_OBSERVATION_L4"
        elif conf >= min_conf * 0.65 and contract.get("hold_on_insufficient_evidence"):
            status = "HOLD"
            achieved = False

        crit["status"] = status
        crit["achieved"] = achieved
        crit["counterfactual_confidence"] = conf

    state["epoch_metadata"] = {
        "epoch": state.get("replay_epoch"),
        "governance_contract": contract.get("governance_contract"),
        "reducer_version": contract.get("reducer_version"),
        "contract_id": contract_id,
        "counterfactual": True,
    }
    return state


def build_counterfactual_replay(
    events: List[Dict[str, Any]],
    *,
    contract_id: str = DEFAULT_COMPARISON_CONTRACT,
    sandbox_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Replay events factually, then apply contract overlay in isolated sandbox."""
    factual = replay_events(events)
    counterfactual = apply_counterfactual_contract(
        factual,
        contract_id=contract_id,
        events=events,
        sandbox_context=sandbox_context,
    )
    return {
        "mode": SANDBOX_MODE,
        "contract_id": contract_id,
        "counterfactual": True,
        "factual_state_hash": compute_replayed_state_hash(factual),
        "counterfactual_state_hash": compute_replayed_state_hash(counterfactual),
        "factual_protected_digest": compute_replayed_protected_digest(factual),
        "counterfactual_protected_digest": compute_replayed_protected_digest(counterfactual),
        "factual_state": factual,
        "counterfactual_state": counterfactual,
        "events_replayed": len(events),
        "note_ar": (
            "Counterfactual replay — analytical sandbox only. "
            "لا يغيّر القرار الأصلي ولا event history."
        ),
    }


def build_baseline_and_counterfactual(
    events: List[Dict[str, Any]],
    *,
    baseline_contract: str = DEFAULT_BASELINE_CONTRACT,
    comparison_contract: str = DEFAULT_COMPARISON_CONTRACT,
    sandbox_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    factual = replay_events(events)
    baseline = apply_counterfactual_contract(
        factual,
        contract_id=baseline_contract,
        events=events,
        sandbox_context=sandbox_context,
    )
    comparison = apply_counterfactual_contract(
        factual,
        contract_id=comparison_contract,
        events=events,
        sandbox_context=sandbox_context,
    )
    return {
        "baseline_contract": baseline_contract,
        "comparison_contract": comparison_contract,
        "counterfactual": True,
        "baseline_state": baseline,
        "comparison_state": comparison,
        "factual_state": factual,
    }


def _criterion_diff(
    baseline: Dict[str, Any],
    comparison: Dict[str, Any],
    key: str,
) -> Optional[Dict[str, Any]]:
    b = (baseline.get("criteria") or {}).get(key) or {}
    c = (comparison.get("criteria") or {}).get(key) or {}
    if not b and not c:
        return None
    b_status = b.get("status") or ("ACHIEVED" if b.get("achieved") else "NOT_ACHIEVED")
    c_status = c.get("status") or ("ACHIEVED" if c.get("achieved") else "NOT_ACHIEVED")
    if b_status == c_status and b.get("achieved") == c.get("achieved"):
        return None
    return {
        "criterion_key": key,
        "criteria_level": b.get("criteria_level") or c.get("criteria_level") or key,
        "baseline_status": b_status,
        "comparison_status": c_status,
        "baseline_achieved": b.get("achieved"),
        "comparison_achieved": c.get("achieved"),
        "baseline_authority": b.get("achievement_authority"),
        "comparison_authority": c.get("achievement_authority"),
        "baseline_confidence": b.get("counterfactual_confidence"),
        "comparison_confidence": c.get("counterfactual_confidence"),
    }


def _build_drift_provenance(
    primary_causes: List[str],
    *,
    b_contract: Dict[str, Any],
    c_contract: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Structured provenance — why drift may occur (descriptive, not normative)."""
    provenance: List[Dict[str, str]] = []
    labels = {
        "runtime_gate_policy_change": (
            "runtime_policy_relaxation",
            "تغيير سياسة runtime gate (L4 sandbox)",
        ),
        "human_playtest_requirement_change": (
            "l5_requirement_removal",
            "إزالة/تخفيف اشتراط Manual Playtest L5",
        ),
    }
    for cause in primary_causes:
        if cause.startswith("runtime_observation_confidence_threshold"):
            provenance.append(
                {
                    "code": "confidence_threshold_reduction",
                    "label_ar": f"تغيير عتبة confidence — {cause.split(': ', 1)[-1]}",
                    "label_en": cause,
                }
            )
            continue
        code, label_ar = labels.get(cause, ("governance_contract_semantics", "اختلاف semantics العقد"))
        provenance.append({"code": code, "label_ar": label_ar, "label_en": cause})

    if b_contract.get("l4_sandbox_permitted") != c_contract.get("l4_sandbox_permitted"):
        if not any(p["code"] == "runtime_policy_relaxation" for p in provenance):
            provenance.insert(
                0,
                {
                    "code": "runtime_policy_relaxation",
                    "label_ar": "تغيير سياسة runtime gate (L4 sandbox)",
                    "label_en": "runtime_gate_policy_change",
                },
            )
    return provenance


def _severity_semantics(
    diff: Dict[str, Any],
    *,
    authority_shift: bool,
    primary_cause: str,
) -> Dict[str, str]:
    """Drift severity taxonomy — descriptive risk framing."""
    b_status = diff.get("baseline_status") or ""
    c_status = diff.get("comparison_status") or ""
    b_auth = str(diff.get("baseline_authority") or "")
    c_auth = str(diff.get("comparison_authority") or "")

    severity = "low"
    drift_scope = "cosmetic"
    academic_risk = "low"

    if b_status == "HOLD" and c_status == "ACHIEVED":
        severity = "moderate"
        drift_scope = "criterion_outcome"
        academic_risk = "moderate"
    if diff.get("baseline_achieved") is False and diff.get("comparison_achieved") is True:
        severity = "high"
        drift_scope = "criterion_outcome"
        academic_risk = "high"
    if authority_shift and "SYSTEM" in b_auth and "L4" in c_auth:
        severity = "high"
        drift_scope = "authority_override"
        academic_risk = "high"
    if authority_shift and "SYSTEM_GOVERNED" in b_auth and "HUMAN" not in c_auth:
        severity = "critical"
        drift_scope = "legitimacy"
        academic_risk = "high"
    if "runtime_gate" in primary_cause:
        drift_scope = "governance_gate"
        if severity == "low":
            severity = "moderate"

    comp_conf = diff.get("comparison_confidence")
    if (
        diff.get("comparison_achieved")
        and comp_conf is not None
        and float(comp_conf) < 0.55
    ):
        academic_risk = "high"
        if severity in ("low", "moderate"):
            severity = "high"
        drift_scope = "evidence_sensitivity"

    return {
        "severity": severity,
        "drift_scope": drift_scope,
        "academic_risk": academic_risk,
    }


def _classify_drift_item(
    diff: Dict[str, Any],
    *,
    baseline_contract: str,
    comparison_contract: str,
    primary_cause: str,
    drift_provenance: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    authority_shift = diff.get("baseline_authority") != diff.get("comparison_authority")
    semantics = _severity_semantics(diff, authority_shift=authority_shift, primary_cause=primary_cause)

    drift_type = "GOVERNANCE_POLICY_DRIFT"
    if "confidence" in primary_cause.lower():
        drift_type = "CONFIDENCE_THRESHOLD_DRIFT"
    elif authority_shift:
        drift_type = "AUTHORITY_DRIFT"
    elif semantics["drift_scope"] == "evidence_sensitivity":
        drift_type = "EVIDENCE_SENSITIVITY_DRIFT"

    return {
        "drift_id": _artifact_id(),
        "drift_type": drift_type,
        "severity": semantics["severity"],
        "drift_scope": semantics["drift_scope"],
        "academic_risk": semantics["academic_risk"],
        "criterion_impact": [diff.get("criteria_level") or diff.get("criterion_key")],
        "authority_shift": authority_shift,
        "baseline_contract": baseline_contract,
        "comparison_contract": comparison_contract,
        "primary_drift_cause": primary_cause,
        "drift_provenance": drift_provenance or [],
        "diff": diff,
        "counterfactual": True,
    }


def detect_governance_drift(
    events: List[Dict[str, Any]],
    *,
    baseline_contract: str = DEFAULT_BASELINE_CONTRACT,
    comparison_contract: str = DEFAULT_COMPARISON_CONTRACT,
    sandbox_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Counterfactual drift detection — events → replay A vs B → semantic diff.
    Isolated analytical replay only.
    """
    pair = build_baseline_and_counterfactual(
        events,
        baseline_contract=baseline_contract,
        comparison_contract=comparison_contract,
        sandbox_context=sandbox_context,
    )
    baseline = pair["baseline_state"]
    comparison = pair["comparison_state"]
    b_contract = get_contract(baseline_contract)
    c_contract = get_contract(comparison_contract)

    primary_causes: List[str] = []
    if b_contract.get("l4_sandbox_permitted") != c_contract.get("l4_sandbox_permitted"):
        primary_causes.append("runtime_gate_policy_change")
    if b_contract.get("min_confidence_achievement") != c_contract.get("min_confidence_achievement"):
        primary_causes.append(
            f"runtime_observation_confidence_threshold: "
            f"{b_contract.get('min_confidence_achievement')} → "
            f"{c_contract.get('min_confidence_achievement')}"
        )
    if b_contract.get("human_playtest_required_for_execution_criteria") != c_contract.get(
        "human_playtest_required_for_execution_criteria"
    ):
        primary_causes.append("human_playtest_requirement_change")
    if not primary_causes:
        primary_causes.append("governance_contract_semantics")

    drift_provenance = _build_drift_provenance(
        primary_causes, b_contract=b_contract, c_contract=c_contract
    )

    drift_items: List[Dict[str, Any]] = []
    for key in ("P5", "P6"):
        diff = _criterion_diff(baseline, comparison, key)
        if diff:
            drift_items.append(
                _classify_drift_item(
                    diff,
                    baseline_contract=baseline_contract,
                    comparison_contract=comparison_contract,
                    primary_cause=primary_causes[0],
                    drift_provenance=drift_provenance,
                )
            )

    gov_drift = (
        (baseline.get("governance") or {}).get("runtime_gated")
        != (comparison.get("governance") or {}).get("runtime_gated")
    )
    if gov_drift and not drift_items:
        drift_items.append(
            {
                "drift_id": _artifact_id(),
                "drift_type": "GOVERNANCE_POLICY_DRIFT",
                "severity": "moderate",
                "drift_scope": "governance_gate",
                "academic_risk": "moderate",
                "criterion_impact": ["C.P5", "C.P6"],
                "authority_shift": True,
                "baseline_contract": baseline_contract,
                "comparison_contract": comparison_contract,
                "primary_drift_cause": primary_causes[0],
                "drift_provenance": drift_provenance,
                "diff": {
                    "governance_baseline": baseline.get("governance"),
                    "governance_comparison": comparison.get("governance"),
                },
                "counterfactual": True,
            }
        )

    artifact = {
        "artifact_id": _artifact_id(),
        "schema": "1.1",
        "mode": "governance_drift_detection",
        "counterfactual": True,
        "generated_at": _utc_now_iso(),
        "baseline_epoch": baseline_contract,
        "comparison_epoch": comparison_contract,
        "baseline_contract": b_contract,
        "comparison_contract": c_contract,
        "primary_drift_causes": primary_causes,
        "drift_provenance": drift_provenance,
        "drift_detected": bool(drift_items),
        "drift_count": len(drift_items),
        "drift_items": drift_items,
        "events_replayed": len(events),
        "disclaimer_ar": (
            "تحليل counterfactual — «لو طُبقت policy أخرى على نفس الأحداث». "
            "لا يُعيد التقييم ولا يغيّر القرار الأصلي."
        ),
        "disclaimer_en": (
            "Counterfactual analysis — «if another policy applied to the same events». "
            "Does not retroactively regrade or alter the original decision. "
            "Descriptive only — not a normative claim that either contract is «better»."
        ),
        "normative_boundary_ar": (
            "وصفي فقط — لا يُقيّم عدالة أو «أفضلية» أي عقد حوكمة."
        ),
        "artifact_hash": "",
    }
    body = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    artifact["artifact_hash"] = hashlib.sha256(_stable_json(body).encode("utf-8")).hexdigest()

    return {
        "drift": artifact,
        "baseline_state_summary": {
            "replay_epoch": baseline.get("replay_epoch"),
            "criteria": baseline.get("criteria"),
            "governance": baseline.get("governance"),
        },
        "comparison_state_summary": {
            "replay_epoch": comparison.get("replay_epoch"),
            "criteria": comparison.get("criteria"),
            "governance": comparison.get("governance"),
        },
    }


def append_drift_artifact_to_snapshot(
    snapshot: Dict[str, Any],
    drift_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Append-only analytical artifact — additive, non-destructive."""
    artifact = drift_report.get("drift") or {}
    if not artifact:
        return snapshot
    history = snapshot.get("counterfactual_drift_artifacts")
    if not isinstance(history, list):
        history = []
    history.append(copy.deepcopy(artifact))
    snapshot["counterfactual_drift_artifacts"] = history
    return snapshot
