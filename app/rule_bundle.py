"""
Decision Provenance — single source of truth for rule bundle versioning.

Every grading decision embeds the same ``decision_provenance`` object (copied, not
rebuilt piecemeal) so replay can answer: which rule bundle produced this outcome?
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

RULE_VERSION = "2026.05"
AUTHORITY_VERSION = "v1"
ENGINE_VERSION = "deterministic_rubric_v2"
GOVERNANCE_FREEZE = "GOVERNANCE_FREEZE_v1"

# Backward-compatible alias used by evidence_registry / deterministic_engine
RUBRIC_RULE_VERSION = RULE_VERSION


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def resolve_execution_mode(grading_mode: Optional[str]) -> str:
    try:
        from app.grading_mode_policy import grading_mode_display_label

        return grading_mode_display_label(grading_mode or "deep")
    except Exception:
        return "PRO"


def active_governance_freeze() -> str:
    try:
        from app.governance_freeze_registry import get_active_freeze_id

        return get_active_freeze_id()
    except Exception:
        return GOVERNANCE_FREEZE


def compute_bundle_hash(
    *,
    rule_version: str,
    authority_version: str,
    engine_version: str,
    governance_freeze: str,
    execution_mode: str,
) -> str:
    payload = {
        "rule_version": rule_version,
        "authority_version": authority_version,
        "engine_version": engine_version,
        "governance_freeze": governance_freeze,
        "execution_mode": (execution_mode or "PRO").upper(),
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def build_decision_provenance(grading_mode: Optional[str] = None) -> Dict[str, Any]:
    """Canonical rule bundle stamp for a grading run."""
    execution_mode = resolve_execution_mode(grading_mode)
    freeze = active_governance_freeze()
    bundle_hash = compute_bundle_hash(
        rule_version=RULE_VERSION,
        authority_version=AUTHORITY_VERSION,
        engine_version=ENGINE_VERSION,
        governance_freeze=freeze,
        execution_mode=execution_mode,
    )
    return {
        "rule_version": RULE_VERSION,
        "authority_version": AUTHORITY_VERSION,
        "engine_version": ENGINE_VERSION,
        "governance_freeze": freeze,
        "execution_mode": execution_mode,
        "bundle_hash": bundle_hash,
    }


def build_decision_provenance_for_execution_mode(execution_mode: str) -> Dict[str, Any]:
    """Build provenance when only BASIC/PRO label is known (per-criterion deterministic rows)."""
    mode = (execution_mode or "PRO").upper()
    grading_mode = "fast" if mode == "BASIC" else "deep"
    return build_decision_provenance(grading_mode)


def copy_provenance(provenance: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shallow copy for embedding in child records (same bundle, shared hash)."""
    return dict(provenance or {})


def format_rule_bundle_label(provenance: Optional[Dict[str, Any]]) -> str:
    p = provenance or {}
    rv = p.get("rule_version") or RULE_VERSION
    av = p.get("authority_version") or AUTHORITY_VERSION
    em = p.get("execution_mode") or "PRO"
    return f"{rv} / Authority {av} / {em}"


def attach_decision_provenance(
    payload: Dict[str, Any],
    *,
    grading_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach top-level decision_provenance if absent."""
    if not payload.get("decision_provenance"):
        payload["decision_provenance"] = build_decision_provenance(
            grading_mode or payload.get("grading_mode")
        )
    return payload


def provenance_from_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve provenance from snapshot / grading_result (top-level or nested)."""
    if not payload:
        return build_decision_provenance(None)
    prov = payload.get("decision_provenance")
    if isinstance(prov, dict) and prov.get("bundle_hash"):
        return prov
    inv = payload.get("artifact_inventory")
    if isinstance(inv, dict):
        inv_prov = inv.get("decision_provenance")
        if isinstance(inv_prov, dict) and inv_prov.get("bundle_hash"):
            return inv_prov
    gdm = payload.get("grade_display_metrics")
    if isinstance(gdm, dict):
        gdm_prov = gdm.get("decision_provenance")
        if isinstance(gdm_prov, dict) and gdm_prov.get("bundle_hash"):
            return gdm_prov
    return build_decision_provenance(payload.get("grading_mode"))
