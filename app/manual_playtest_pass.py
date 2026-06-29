"""
Manual Playtest Pass — interactive verification without legitimacy inference.

Links to RUNTIME_OBSERVATION_SESSION_v1; does not unlock legitimacy or rubric claims.
"""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.interactive_phenomenology import (
    build_interactive_phenomenology_record,
    describe_interactive_phenomenology_en,
    validate_playtest_record_text,
)

SPEC_PATH = Path(__file__).resolve().parent / "calibration" / "MANUAL_PLAYTEST_PASS_v1.json"
PASS_DIR = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "manual_playtest_passes"
)
SESSION_DIR = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "runtime_observation_sessions"
)

SPEC_ID = "MANUAL_PLAYTEST_PASS_v1"
PASS_TYPE_ID = "MANUAL_PLAYTEST_PASS_v1"


def submission_playtest_dirs(submission_id: int) -> tuple[Path, Path]:
    """Per-submission storage under uploads/debug (production grading path)."""
    base = Path("uploads") / "debug"
    session_dir = base / "runtime_observation_sessions"
    pass_dir = base / "playtest_passes" / str(submission_id)
    return session_dir, pass_dir


def _resolve_session_dir(session_dir: Optional[Path] = None) -> Path:
    return session_dir or SESSION_DIR


def _resolve_pass_dir(pass_dir: Optional[Path] = None) -> Path:
    return pass_dir or PASS_DIR


def _session_path(parent_session_id: str, session_dir: Optional[Path] = None) -> Path:
    return _resolve_session_dir(session_dir) / f"{parent_session_id}.json"


def ensure_runtime_session_file(
    parent_session_id: str,
    *,
    session_dir: Optional[Path] = None,
    submission_id: Optional[int] = None,
    student_label: str = "",
    artifact_paths: Optional[List[str]] = None,
    sandbox_snapshot: Optional[Dict[str, Any]] = None,
) -> Path:
    """Create minimal parent session JSON if missing (submission-scoped path)."""
    path = _session_path(parent_session_id, session_dir)
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    sandbox = sandbox_snapshot or {}
    parent: Dict[str, Any] = {
        "session_id": parent_session_id,
        "session_type_id": "RUNTIME_OBSERVATION_SESSION_v1",
        "mode": "runtime_observation_session",
        "not_mode": "final_legitimacy_session",
        "submission_id": submission_id,
        "session_label": student_label,
        "artifact_paths": list(artifact_paths or []),
        "sandbox_status": sandbox.get("status", "linked_from_grading_snapshot"),
        "manual_playtest_passes": [],
        "interactive_verification_layer": {},
        "human_authority_required": True,
        "invariant_en": "Runtime visibility ≠ runtime legitimacy.",
    }
    path.write_text(json.dumps(parent, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_spec() -> Dict[str, Any]:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _blank_test_row(test: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "test_id": test["test_id"],
        "prompt_en": test.get("prompt_en", ""),
        "hypothesis_links": list(test.get("hypothesis_links") or []),
        "status": "pending",
        "observed_en": "",
        "phenomenology_descriptors": [],
        "do_not_infer_en": test.get("do_not_infer_en", ""),
        "observed_allowed_examples_en": list(test.get("observed_allowed_examples_en") or []),
    }


def create_playtest_pass(
    parent_session_id: str,
    *,
    pass_label: str = "pass_1",
    student_label: str = "",
    artifact_path: str = "",
    pass_mode: str = "visual_human",
    prior_pass_id: str = "",
    session_dir: Optional[Path] = None,
    pass_dir: Optional[Path] = None,
    create_parent_if_missing: bool = False,
    submission_id: Optional[int] = None,
    artifact_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    spec = load_spec()
    parent_path = _session_path(parent_session_id, session_dir)
    if not parent_path.exists():
        if not create_parent_if_missing:
            raise FileNotFoundError(f"parent runtime session not found: {parent_session_id}")
        ensure_runtime_session_file(
            parent_session_id,
            session_dir=session_dir,
            submission_id=submission_id,
            student_label=student_label,
            artifact_paths=artifact_paths or ([artifact_path] if artifact_path else []),
        )

    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    modes = spec.get("pass_modes") or {}
    if pass_mode not in modes:
        raise ValueError(f"unknown pass_mode: {pass_mode} (expected assisted or visual_human)")

    pass_id = f"mpp_{uuid.uuid4().hex[:12]}"

    record: Dict[str, Any] = {
        "pass_id": pass_id,
        "pass_type_id": PASS_TYPE_ID,
        "spec_id": SPEC_ID,
        "logged_at": datetime.datetime.utcnow().isoformat() + "Z",
        "mode": "manual_playtest_pass",
        "pass_mode": pass_mode,
        "not_mode": "final_legitimacy_session",
        "parent_session_id": parent_session_id,
        "prior_pass_id": prior_pass_id or None,
        "pass_label": pass_label,
        "student_label": student_label or parent.get("session_label") or "",
        "artifact_path": artifact_path or (parent.get("artifact_paths") or [""])[0],
        "invariant_en": spec.get("invariant_en"),
        "core_separation_en": spec.get("core_separation_en"),
        "umbrella_phenomenology": spec.get("umbrella_phenomenology"),
        "assigns_legitimacy": False,
        "assigns_rubric_inference": False,
        "tests": [_blank_test_row(t) for t in spec.get("default_test_sequence") or []],
        "interactive_phenomenology_descriptors": [],
        "interactive_phenomenology_summary_en": "",
        "contradiction_updates_advisory": [],
        "runtime_quarantine_unchanged": True,
        "forbidden_recorder_language_en": spec.get("forbidden_recorder_language_en") or [],
        "visual_pass_recording_discipline": spec.get("visual_pass_recording_discipline"),
        "human_authority_required": True,
        "institutional_ledger_appended": False,
        "playtest_status": "pending",
        "submission_id": submission_id,
    }
    if pass_mode == "visual_human":
        record["recording_instruction_en"] = (
            "Record observable state transitions only. Do not complete evaluation."
        )
        record["central_contradiction_test_id"] = (
            (spec.get("epistemic_boundaries_discovered") or {}).get("central_contradiction_test_id")
        )
    return record


def save_playtest_pass(record: Dict[str, Any], *, pass_dir: Optional[Path] = None) -> Path:
    out_dir = _resolve_pass_dir(pass_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{record['pass_id']}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    record["pass_file"] = str(out)
    return out


def record_test_observation(
    record: Dict[str, Any],
    test_id: str,
    *,
    observed_en: str,
    phenomenology_descriptors: Optional[List[str]] = None,
    status: str = "observed",
) -> Dict[str, Any]:
    check = validate_playtest_record_text(observed_en)
    if not check["allowed"]:
        raise ValueError(f"observed_en failed escalation check: {check['violations']}")

    found = False
    for test in record.get("tests") or []:
        if test.get("test_id") != test_id:
            continue
        found = True
        test["status"] = status
        test["observed_en"] = observed_en.strip()
        test["phenomenology_descriptors"] = list(phenomenology_descriptors or [])
        test["recorded_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        break
    if not found:
        raise KeyError(f"unknown test_id: {test_id}")

    _rebuild_pass_phenomenology(record)
    return record


def _rebuild_pass_phenomenology(record: Dict[str, Any]) -> None:
    desc: List[str] = []
    seen: set[str] = set()
    for test in record.get("tests") or []:
        if test.get("status") not in ("observed", "inconclusive"):
            continue
        for d in test.get("phenomenology_descriptors") or []:
            if d not in seen:
                seen.add(d)
                desc.append(d)

    if desc:
        record["interactive_phenomenology"] = build_interactive_phenomenology_record(desc)
        record["interactive_phenomenology_descriptors"] = desc
        record["interactive_phenomenology_summary_en"] = describe_interactive_phenomenology_en(desc)
    else:
        record.pop("interactive_phenomenology", None)
        record["interactive_phenomenology_descriptors"] = []
        record["interactive_phenomenology_summary_en"] = ""

    pending = sum(1 for t in record.get("tests") or [] if t.get("status") == "pending")
    mode = record.get("pass_mode") or "visual_human"
    if pending:
        record["playtest_status"] = "pending"
    elif mode == "assisted":
        inconclusive = sum(1 for t in record.get("tests") or [] if t.get("status") == "inconclusive")
        record["playtest_status"] = "partial_assisted" if inconclusive else "complete"
    else:
        record["playtest_status"] = "complete_visual"


def finalize_playtest_pass(
    record: Dict[str, Any],
    *,
    session_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Attach pass to parent session — quarantine and legitimacy remain blocked."""
    parent_path = _session_path(record["parent_session_id"], session_dir)
    if not parent_path.exists():
        raise FileNotFoundError(f"parent session not found: {record['parent_session_id']}")

    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    spec = load_spec()
    iv = parent.get("interactive_verification_layer") or {}
    passes = parent.get("manual_playtest_passes") or []
    summary = {
        "pass_id": record["pass_id"],
        "pass_label": record.get("pass_label"),
        "pass_mode": record.get("pass_mode"),
        "playtest_status": record.get("playtest_status"),
        "pass_file": record.get("pass_file"),
        "interactive_phenomenology_descriptors": record.get("interactive_phenomenology_descriptors") or [],
    }
    passes = [p for p in passes if p.get("pass_id") != record["pass_id"]]
    passes.append(summary)
    parent["manual_playtest_passes"] = passes
    parent["interactive_verification_layer"] = {
        "status": record.get("playtest_status"),
        "pass_mode": record.get("pass_mode"),
        "invariant_en": "Mechanic observation does not imply pedagogical or rubric inference.",
        "input_dispatched": iv.get("input_dispatched") or record.get("pass_mode") == "assisted",
        "assisted_pass_id": iv.get("assisted_pass_id"),
        "interaction_visually_corroborated": record.get("playtest_status") == "complete_visual",
        "mechanics_interactively_observed": record.get("playtest_status") == "complete_visual",
        "mechanics_corroborated": "partial" if record.get("playtest_status") == "complete_visual" else False,
        "gameplay_understood": False,
        "gameplay_meaning": "opaque",
        "pedagogical_meaning": "opaque",
        "rubric_validated": False,
        "legitimacy_granted": False,
        "latest_pass_id": record["pass_id"],
        "central_pending_test_id": (
            None
            if record.get("playtest_status") == "complete_visual"
            else (spec.get("epistemic_boundaries_discovered") or {}).get("central_contradiction_test_id")
        ),
    }
    parent_path.write_text(json.dumps(parent, ensure_ascii=False, indent=2), encoding="utf-8")
    record["parent_session_updated"] = True
    return record


def load_playtest_pass(pass_id: str, *, pass_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = _resolve_pass_dir(pass_dir) / f"{pass_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_playtest_passes(*, pass_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    out_dir = _resolve_pass_dir(pass_dir)
    if not out_dir.is_dir():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(out_dir.glob("mpp_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return records


def format_playtest_checklist(record: Dict[str, Any]) -> str:
    mode = record.get("pass_mode") or "visual_human"
    title = "HUMAN VISUAL PASS" if mode == "visual_human" else "ASSISTED PASS"
    lines = [
        f"=== MANUAL PLAYTEST — {title} (not legitimacy) ===",
        f"pass_id: {record.get('pass_id')}",
        f"pass_mode: {mode}",
        f"parent_session: {record.get('parent_session_id')}",
        f"artifact: {record.get('artifact_path')}",
        "",
        record.get("invariant_en") or "",
        f"separation: {record.get('core_separation_en')}",
        "",
    ]
    if record.get("recording_instruction_en"):
        lines.extend([record["recording_instruction_en"], ""])
    if record.get("central_contradiction_test_id"):
        lines.append(f"CENTRAL TEST: {record['central_contradiction_test_id']}")
        lines.append("")
    lines.append("RECORD ONLY observed · DO NOT INFER legitimacy/rubric/invalidity")
    lines.append("")
    for i, test in enumerate(record.get("tests") or [], 1):
        lines.extend([
            f"{i}. [{test.get('test_id')}] {test.get('prompt_en')}",
            f"   status: {test.get('status')}",
            f"   do_not_infer: {test.get('do_not_infer_en')}",
        ])
        if test.get("hypothesis_links"):
            lines.append(f"   hypothesis_links: {', '.join(test['hypothesis_links'])}")
        if test.get("observed_en"):
            lines.append(f"   observed: {test['observed_en']}")
        lines.append("")
    lines.extend([
        "FORBIDDEN recorder language:",
        "  game validated · rubric achieved/failed · project invalid · gameplay broken",
    ])
    return "\n".join(lines)
