"""
Runtime observation ledger — append-only capture, not grading, not legitimacy.

Invariant: Runtime observation does not imply runtime legitimacy.
"""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime_observation_contract import validate_l4_claim_text
from app.execution_phenomenology import (
    build_phenomenology_record,
    validate_phenomenology_text,
)
from app.telemetry_replay_capture import validate_replay_phenomenology_text

ARTIFACT_ID = "RUNTIME_OBSERVATION_LEDGER_SCHEMA_v1"
PHASE_ID = "RUNTIME_OBSERVABILITY_PREPARATION_v1"
LEDGER = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "runtime_observation_ledger.jsonl"
)

FORBIDDEN_ENTRY_SIGNALS = frozenset({
    "criterion_achieved",
    "verified_achievement",
    "game_completed",
    "runtime_legitimacy_granted",
    "auto_achieved",
})


def _scan_forbidden_signals(record: Dict[str, Any]) -> List[str]:
    """Scan user-facing text fields only — not l4_language_check diagnostic blobs."""
    text_fields = (
        record.get("narrative_summary") or "",
        record.get("facilitator_notes_ar") or "",
        json.dumps(record.get("sandbox_result") or {}, ensure_ascii=False),
    )
    blob = " ".join(text_fields).lower()
    hits: List[str] = []
    for signal in FORBIDDEN_ENTRY_SIGNALS:
        if signal.replace("_", " ") in blob or signal in blob:
            hits.append(signal)
    return hits


def normalize_observation(
    *,
    observation_mode: str,
    artifact_name: str = "",
    artifact_type: str = "",
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    session_label: str = "",
    telemetry_graph: Optional[Dict[str, Any]] = None,
    provenance_chain: Optional[List[Dict[str, Any]]] = None,
    sandbox_result: Optional[Dict[str, Any]] = None,
    phenomenology: Optional[List[str]] = None,
    replay_phenomenology: Optional[List[str]] = None,
    telemetry_replay_wiring: Optional[Dict[str, Any]] = None,
    runtime_epistemic_governance: Optional[Dict[str, Any]] = None,
    facilitator_notes_ar: str = "",
    narrative_summary: str = "",
) -> Dict[str, Any]:
    l4_check = validate_l4_claim_text(narrative_summary)
    phen_check = validate_phenomenology_text(narrative_summary)
    replay_check = validate_replay_phenomenology_text(narrative_summary)
    if not l4_check.get("allowed"):
        raise ValueError(
            "narrative_summary violates L4 contract: "
            + ", ".join(v.get("phrase", v.get("pattern", "?")) for v in l4_check.get("violations", []))
        )
    if not phen_check.get("allowed"):
        raise ValueError(
            "narrative_summary violates phenomenology contract: "
            + ", ".join(v.get("phrase", v.get("pattern", "?")) for v in phen_check.get("violations", []))
        )
    if not replay_check.get("allowed"):
        raise ValueError(
            "narrative_summary violates replay phenomenology contract: "
            + ", ".join(v.get("phrase", v.get("pattern", "?")) for v in replay_check.get("violations", []))
        )
    phen_record = None
    if phenomenology:
        phen_record = build_phenomenology_record(phenomenology)
    replay_phen_record = None
    if replay_phenomenology:
        from app.telemetry_replay_capture import build_replay_phenomenology_record
        replay_phen_record = build_replay_phenomenology_record(replay_phenomenology)
    record: Dict[str, Any] = {
        "phase_id": PHASE_ID,
        "observation_mode": observation_mode,
        "artifact_name": artifact_name or "",
        "artifact_type": artifact_type or "",
        "submission_id": submission_id,
        "batch_id": batch_id,
        "session_label": session_label or "",
        "telemetry_graph": telemetry_graph,
        "provenance_chain": provenance_chain or [],
        "sandbox_result": sandbox_result,
        "facilitator_notes_ar": facilitator_notes_ar or "",
        "narrative_summary": narrative_summary or "",
        "l4_language_check": l4_check,
        "phenomenology_check": phen_check,
        "replay_phenomenology_check": replay_check,
        "execution_phenomenology": phen_record,
        "replay_phenomenology": replay_phen_record,
        "telemetry_replay_wiring": telemetry_replay_wiring,
        "runtime_epistemic_governance": runtime_epistemic_governance,
    }
    forbidden = _scan_forbidden_signals(record)
    if forbidden:
        raise ValueError(f"forbidden legitimacy signals in record: {', '.join(forbidden)}")
    return record


def append_runtime_observation(
    record: Dict[str, Any],
    *,
    ledger_path: Optional[Path] = None,
) -> str:
    path = ledger_path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "observation_id": f"rol_{uuid.uuid4().hex[:12]}",
        "artifact_id": ARTIFACT_ID,
        "logged_at": datetime.datetime.utcnow().isoformat() + "Z",
        "assigns_authority": False,
        "assigns_legitimacy": False,
        "invariant_en": "Runtime observation does not imply runtime legitimacy.",
        **record,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["observation_id"]
