"""
Governance freeze registry — which freeze epoch is institutionally active.

L4 sandbox and runtime authority expansion require GOVERNANCE_FREEZE_v2 activation
via signed epoch workshop verdict — not metrics alone.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.canonical_stability_trajectory import ACTIVE_FREEZE_EPOCH, FREEZE_EPOCHS

FREEZE_V1_PATH = Path("app/calibration/GOVERNANCE_FREEZE_v1.json")
FREEZE_V2_PATH = Path("app/calibration/GOVERNANCE_FREEZE_v2.json")
STATE_PATH = Path("app/calibration/governance_freeze_state.json")

VERDICT_ACTIVATES_V2 = "epoch_transition_justified_institutionally"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _find_signed_v2_verdicts() -> List[Dict[str, Any]]:
    from app.governance_epoch_workshop import load_epoch_workshop_reviews

    rows = load_epoch_workshop_reviews(
        current_epoch_id="epoch_1",
        target_epoch_id="epoch_2",
    )
    return [
        r for r in rows
        if r.get("transition_verdict") == VERDICT_ACTIVATES_V2
        and (r.get("signed_institutional_artifact") or {}).get("artifact_id")
    ]


def get_active_freeze_epoch_id() -> str:
    """Institutionally active freeze epoch (file override or default v1)."""
    state = _load_state()
    if state.get("active_epoch_id"):
        return str(state["active_epoch_id"])
    if _find_signed_v2_verdicts():
        return "epoch_2"
    return ACTIVE_FREEZE_EPOCH


def get_active_freeze_id() -> str:
    epoch_id = get_active_freeze_epoch_id()
    entry = FREEZE_EPOCHS.get(epoch_id, {})
    return str(entry.get("freeze_id") or "GOVERNANCE_FREEZE_v1")


def is_governance_freeze_v2_active() -> bool:
    return get_active_freeze_epoch_id() == "epoch_2"


def is_l4_sandbox_permitted() -> bool:
    """
    L4 minimal sandbox runs after signed institutional v2 transition,
    explicit freeze state epoch_2, or AI_GRADER_ENABLE_L4=1 (deployment override).
    """
    env_flag = os.environ.get("AI_GRADER_ENABLE_L4", "").strip().lower()
    if env_flag in ("1", "true", "yes", "on"):
        return True
    state = _load_state()
    if str(state.get("active_epoch_id") or "") == "epoch_2":
        return True
    signed = _find_signed_v2_verdicts()
    if not signed:
        return False
    return get_active_freeze_epoch_id() == "epoch_2"


def get_l4_gate_status() -> Dict[str, Any]:
    """Why L4 is or is not permitted — for decision dashboards."""
    signed = _find_signed_v2_verdicts()
    v2_active = is_governance_freeze_v2_active()
    permitted = is_l4_sandbox_permitted()
    return {
        "active_freeze_epoch_id": get_active_freeze_epoch_id(),
        "active_freeze_id": get_active_freeze_id(),
        "governance_freeze_v2_active": v2_active,
        "l4_sandbox_permitted": permitted,
        "signed_v2_verdict_count": len(signed),
        "latest_signed_artifact_id": (
            (signed[-1].get("signed_institutional_artifact") or {}).get("artifact_id")
            if signed else None
        ),
        "gate_reason_ar": (
            "L4 sandbox مسموح — observational only — بعد signed epoch verdict."
            if permitted
            else "L4 sandbox مقفول — أكمل Epoch Workshop Review + signed verdict أولاً."
        ),
        "confidence_acceleration_forbidden_ar": (
            "نجاح pilot يثبت استقرار الحوكمة فقط — لا يثبت correctness ولا AI intelligence."
        ),
    }


def activate_freeze_epoch_from_verdict(
    *,
    target_epoch_id: str,
    artifact_id: str,
    transition_verdict: str,
) -> Dict[str, Any]:
    """
    Record institutional activation after signed workshop verdict.
    Called from save_epoch_workshop_review — not from metrics automation.
    """
    if transition_verdict != VERDICT_ACTIVATES_V2:
        return {"activated": False, "reason": "verdict_not_transition_justified"}

    if target_epoch_id != "epoch_2":
        return {"activated": False, "reason": "unsupported_target_epoch"}

    state = {
        "active_epoch_id": "epoch_2",
        "active_freeze_id": "GOVERNANCE_FREEZE_v2",
        "activated_from_artifact_id": artifact_id,
        "transition_verdict": transition_verdict,
        "authority_note_ar": (
            "evolve institutional authority semantics — L4 observational only — "
            "human authority mandatory."
        ),
    }
    _save_state(state)
    return {"activated": True, "state": state}


def build_freeze_registry_report() -> Dict[str, Any]:
    v1 = _load_json(FREEZE_V1_PATH)
    v2 = _load_json(FREEZE_V2_PATH)
    gate = get_l4_gate_status()
    return {
        "report_type": "governance_freeze_registry",
        "active": {
            "epoch_id": gate["active_freeze_epoch_id"],
            "freeze_id": gate["active_freeze_id"],
        },
        "freeze_v1_status": v1.get("status", "frozen"),
        "freeze_v2_status": v2.get("status", "draft_pending_signed_verdict"),
        "l4_gate": gate,
        "freeze_epochs": FREEZE_EPOCHS,
    }
