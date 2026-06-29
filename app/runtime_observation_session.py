"""
Runtime observation session — practical evaluation without auto-legitimacy.

Session type: RUNTIME_OBSERVATION_SESSION_v1
NOT: final legitimacy session.

Output: runtime_observation_sessions/ — institutional ledger stays empty by default.
"""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.execution_phenomenology import build_phenomenology_record, describe_phenomenology_en
from app.runtime_epistemic_governance import build_runtime_epistemic_governance_bundle
from app.runtime_observation_sandbox import observe_runtime_artifacts
from app.telemetry_replay_capture import wire_from_sandbox_analyses

SESSION_TYPE_ID = "RUNTIME_OBSERVATION_SESSION_v1"
SESSION_DIR = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "runtime_observation_sessions"
)

FORBIDDEN_SESSION_LANGUAGE = (
    "game validated",
    "rubric achieved",
    "project confirmed",
    "gameplay verified",
    "mechanics validated",
)


def _infer_phenomenology_from_analyses(analyses: List[Dict[str, Any]]) -> List[str]:
    """Map sandbox analyses to phenomenology descriptors — observation only."""
    desc: List[str] = []
    for a in analyses:
        atype = a.get("type")
        smoke = a.get("smoke_result")
        if atype == "exe" and a.get("attempted"):
            desc.append("process_launched")
        if smoke in ("stable_window", "launch_ok"):
            desc.extend(["window_detected", "frames_rendered", "execution_continuity_observed"])
            desc.append("telemetry_stream_active")
        if (a.get("signals") or {}).get("player_moved") == "detected":
            desc.append("input_responded")
        if a.get("valid") and atype in ("apk", "pck", "exe"):
            desc.append("executable_persisted")
        crash = (a.get("signals") or {}).get("crash")
        if crash == "observed" and smoke not in ("stable_window", "launch_ok"):
            desc.append("crash_observed")
    # dedupe preserve order
    seen: set[str] = set()
    out: List[str] = []
    for d in desc:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _infer_replay_phenomenology(analyses: List[Dict[str, Any]]) -> List[str]:
    replay: List[str] = ["replay_captured"]
    smoke_ok = any(a.get("smoke_result") in ("stable_window", "launch_ok") for a in analyses)
    if smoke_ok:
        replay.append("replay_continuous")
    if len(analyses) >= 2:
        replay.append("replay_reproducible")
    return replay


def run_runtime_observation_session(
    artifact_paths: List[Union[str, Path]],
    *,
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    session_label: str = "",
    enable_smoke_test: bool = True,
    facilitator_notes_ar: str = "",
    save_session: bool = True,
    append_institutional_ledger: bool = False,
) -> Dict[str, Any]:
    """
    Run a runtime observation session — phenomenology + governance, no auto-legitimacy.

    append_institutional_ledger defaults False — ledger remains empty by policy.
    """
    if append_institutional_ledger:
        raise ValueError(
            "append_institutional_ledger=False by constitutional policy — "
            "use save_session to runtime_observation_sessions/ instead"
        )

    paths = [str(p) for p in artifact_paths]
    sandbox = observe_runtime_artifacts(paths, enable_smoke_test=enable_smoke_test)
    analyses = sandbox.get("artifact_analyses") or []

    exec_desc = _infer_phenomenology_from_analyses(analyses)
    replay_desc = _infer_replay_phenomenology(analyses) if analyses else []

    wiring = wire_from_sandbox_analyses(
        analyses,
        observation_mode="runtime_observation_session",
        replay_descriptors=replay_desc or None,
    )
    governance = build_runtime_epistemic_governance_bundle(wiring)

    exec_phen = build_phenomenology_record(exec_desc) if exec_desc else None
    phenomenology_summary_en = (
        describe_phenomenology_en(exec_desc) if exec_desc else "No execution phenomenology inferred."
    )

    quarantine_states = governance.get("runtime_quarantine_states") or []
    mandatory_ok = (
        "runtime_epistemically_unverified" in quarantine_states
        and "runtime_legitimacy_blocked" in quarantine_states
    )

    session: Dict[str, Any] = {
        "session_id": f"ros_{uuid.uuid4().hex[:12]}",
        "session_type_id": SESSION_TYPE_ID,
        "logged_at": datetime.datetime.utcnow().isoformat() + "Z",
        "mode": "runtime_observation_session",
        "not_mode": "final_legitimacy_session",
        "submission_id": submission_id,
        "batch_id": batch_id,
        "session_label": session_label or "",
        "artifact_paths": paths,
        "sandbox_status": sandbox.get("status"),
        "observation_mode": sandbox.get("observation_mode"),
        "execution_phenomenology": exec_phen,
        "execution_phenomenology_descriptors": exec_desc,
        "replay_phenomenology_descriptors": replay_desc,
        "phenomenology_summary_en": phenomenology_summary_en,
        "telemetry_replay_wiring": wiring,
        "runtime_epistemic_governance": governance,
        "runtime_quarantine_states": quarantine_states,
        "mandatory_quarantine_present": mandatory_ok,
        "allowed_claims_en": exec_desc + [f"replay:{d}" for d in replay_desc],
        "forbidden_auto_claims_en": [
            "game validated",
            "rubric achieved",
            "project confirmed",
        ],
        "human_authority_required": True,
        "facilitator_notes_ar": facilitator_notes_ar or "",
        "invariant_en": "Runtime visibility ≠ runtime legitimacy.",
        "institutional_ledger_appended": False,
    }

    summary_lower = phenomenology_summary_en.lower()
    if any(f in summary_lower for f in FORBIDDEN_SESSION_LANGUAGE):
        raise ValueError("session summary contains forbidden legitimacy language")

    if save_session:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SESSION_DIR / f"{session['session_id']}.json"
        out_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        session["session_file"] = str(out_path)

    return session


def format_session_report(session: Dict[str, Any]) -> str:
    """Human-readable observation report — no legitimacy language."""
    lines = [
        "=== RUNTIME OBSERVATION SESSION (not final legitimacy) ===",
        f"session_id: {session.get('session_id')}",
        f"mode: {session.get('mode')}",
        "",
        "PHENOMENOLOGY (what appeared — not what it means):",
    ]
    for d in session.get("execution_phenomenology_descriptors") or []:
        lines.append(f"  - {d}")
    for d in session.get("replay_phenomenology_descriptors") or []:
        lines.append(f"  - replay:{d}")
    lines.extend([
        "",
        session.get("phenomenology_summary_en") or "",
        "",
        "QUARANTINE STATES (mandatory):",
    ])
    for s in session.get("runtime_quarantine_states") or []:
        lines.append(f"  - {s}")
    lines.extend([
        "",
        "FORBIDDEN without human L5:",
        "  game validated · rubric achieved · project confirmed",
        "",
        f"invariant: {session.get('invariant_en')}",
    ])
    return "\n".join(lines)
