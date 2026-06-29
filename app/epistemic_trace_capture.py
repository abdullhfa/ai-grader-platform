"""
EPISTEMIC_TRACE_CAPTURE — observational evidence layer (not grading).

Records timing, transitions, quarantine state, language — no authority assignment.
"""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

OBSERVABILITY_INVARIANT_EN = (
    "Observability may illuminate authority formation. "
    "It may not silently inherit authority formation."
)
OBSERVABILITY_INVARIANT_AR = (
    "الرصد قد يُضيء تشكّل السلطة. "
    "لا يجوز أن يرث تشكّل السلطة بصمت."
)

SCHEMA_ID = "EPISTEMIC_TRACE_CAPTURE_SCHEMA_v1"
UI_INVARIANT_EN = (
    "This interface records epistemic state transitions. "
    "It does not assign authority."
)
UI_INVARIANT_AR = (
    "هذه الواجهة تسجّل انتقالات الحالة المعرفية. "
    "لا تمنح سلطة."
)

TRACE_LEDGER = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "epistemic_trace_captures.jsonl"
)


def empty_epistemic_trace(*, section_a: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Section F template — optional fields, no scoring."""
    a = section_a or {}
    return {
        "schema_id": SCHEMA_ID,
        "ui_invariant_ar": UI_INVARIANT_AR,
        "replay_chronology": {
            "replay_opened_at": None,
            "replay_consulted_at": None,
            "authority_language_first_seen_at": None,
            "replay_precedes_authority": None,
        },
        "authority_formation_markers": {
            "verification_lexicon_detected": None,
            "closure_trigger_detected": "",
            "temptation_classification": None,
            "authority_formation_altered": None,
        },
        "quarantine_state_capture": {
            "quarantine_state": None,
            "qb_level": None,
            "quarantine_breach_reason": "",
            "restraint_anchor_detected": "",
        },
        "provenance_continuity": {
            "exe_present": a.get("executable_detected"),
            "exe_identity_matches_submission": None,
            "runtime_corroborated": None,
            "provenance_continuity_state": None,
        },
        "counterfactual_capture": {
            "counterfactual_without_replay": "",
            "intuition_closure_detected": None,
            "replay_changed_outcome": None,
        },
        "possible_vocabulary_escalation_hint": None,
    }


def _parse_ts(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def compute_replay_precedes_authority(trace: Dict[str, Any]) -> Optional[bool]:
    """Advisory — True if replay consult strictly before first authority language."""
    chrono = trace.get("replay_chronology") or {}
    consult = _parse_ts(chrono.get("replay_consulted_at"))
    authority = _parse_ts(chrono.get("authority_language_first_seen_at"))
    if consult and authority:
        return consult < authority
    if consult and not authority:
        return None
    return None


def normalize_epistemic_trace(
    raw: Optional[Dict[str, Any]],
    *,
    section_a: Optional[Dict[str, Any]] = None,
    replay_consulted_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge facilitator input into canonical Section F shape."""
    base = empty_epistemic_trace(section_a=section_a)
    if not raw:
        if replay_consulted_at:
            base["replay_chronology"]["replay_consulted_at"] = replay_consulted_at
        return base

    for group in (
        "replay_chronology",
        "authority_formation_markers",
        "quarantine_state_capture",
        "provenance_continuity",
        "counterfactual_capture",
    ):
        incoming = raw.get(group) or {}
        if isinstance(incoming, dict):
            base[group].update({k: v for k, v in incoming.items() if v != ""})

    if replay_consulted_at and not base["replay_chronology"].get("replay_consulted_at"):
        base["replay_chronology"]["replay_consulted_at"] = replay_consulted_at

    computed = compute_replay_precedes_authority(base)
    if computed is not None and base["replay_chronology"].get("replay_precedes_authority") is None:
        base["replay_chronology"]["replay_precedes_authority"] = computed

    hint_raw = raw.get("possible_vocabulary_escalation_hint")
    if hint_raw is not None:
        from app.possible_vocabulary_escalation_hint import normalize_vocabulary_hint_payload

        base["possible_vocabulary_escalation_hint"] = normalize_vocabulary_hint_payload(hint_raw)

    return base


def enrich_trace_advisory(
    trace: Dict[str, Any],
    observation_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach advisory quarantine/QB hints — facilitator values take precedence."""
    try:
        from app.epistemic_quarantine_contract import evaluate_from_observation_record

        ev = evaluate_from_observation_record(observation_record)
        qsc = trace.setdefault("quarantine_state_capture", {})
        if not qsc.get("quarantine_state"):
            state = ev.get("quarantine_state")
            if state == "breach_detected":
                qsc["quarantine_state"] = "breached"
            elif state in ("quarantine_maintained", "quarantine_entered", "lifting_in_progress"):
                qsc["quarantine_state"] = "maintained"
            elif state == "idle":
                qsc["quarantine_state"] = "active"
        if not qsc.get("qb_level") and ev.get("breach_severity"):
            qsc["qb_level"] = ev.get("breach_severity")
        trace["advisory_enrichment"] = {
            "quarantine_state_advisory": ev.get("quarantine_state"),
            "breach_severity_advisory": ev.get("breach_severity"),
            "entry_triggers_advisory": ev.get("entry_triggers"),
            "wire_to_grading": False,
        }
    except Exception:
        pass
    return trace


def append_epistemic_trace(
    record: Dict[str, Any],
    *,
    ledger_path: Optional[Path] = None,
) -> Optional[str]:
    """Append Section F trace to dedicated jsonl (observational residue)."""
    trace = record.get("section_f_epistemic_trace")
    if not trace:
        return None
    path = ledger_path or TRACE_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "trace_id": f"etc_{uuid.uuid4().hex[:12]}",
        "submission_id": record.get("submission_id"),
        "batch_id": record.get("batch_id"),
        "logged_at": record.get("logged_at"),
        "schema_id": SCHEMA_ID,
        "section_f_epistemic_trace": trace,
        "source": "governance_pilot_observatory",
        "assigns_authority": False,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["trace_id"]
