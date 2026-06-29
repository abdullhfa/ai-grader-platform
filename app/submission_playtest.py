"""
Submission-scoped Manual Playtest — L5 human verification layer for teachers.

Links runtime replay → playtest checklist → grading_snapshot (advisory only).
Does not auto-mutate final grades in the database.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.manual_playtest_pass import (
    create_playtest_pass,
    finalize_playtest_pass,
    list_playtest_passes,
    load_playtest_pass,
    load_spec,
    record_test_observation,
    save_playtest_pass,
    submission_playtest_dirs,
    ensure_runtime_session_file,
)
from app.runtime_criterion_mapping import evaluate_operational_support


def _artifact_path_from_snapshot(snapshot: Optional[Dict[str, Any]]) -> str:
    inv = (snapshot or {}).get("artifact_inventory") or {}
    analyses = (inv.get("runtime_observation_report") or {}).get("artifact_analyses") or []
    for analysis in analyses:
        if isinstance(analysis, dict) and analysis.get("artifact"):
            return str(analysis["artifact"])
    exe_files = (inv.get("runtime_artifacts") or {}).get("executable_files") or []
    if exe_files and isinstance(exe_files[0], dict):
        return str(exe_files[0].get("name") or "")
    return ""


def runtime_session_id_from_snapshot(snapshot: Optional[Dict[str, Any]]) -> str:
    inv = (snapshot or {}).get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    session_id = obs.get("runtime_session_id")
    if session_id:
        return str(session_id)
    ctx = obs.get("runtime_session_context") or {}
    if ctx.get("runtime_session_id"):
        return str(ctx["runtime_session_id"])
    return ""


def _has_executable_artifacts(inv: Dict[str, Any]) -> bool:
    exe = inv.get("executable_artifacts") or {}
    rt = inv.get("runtime_artifacts") or {}
    return bool(exe.get("files") or rt.get("executables_detected"))


def _primary_game_executable_path(inv: Dict[str, Any]) -> str:
    """Best-effort game .exe path for teacher manual playtest (not UnityCrashHandler)."""
    skip = ("unitycrashhandler", "uninstall", "setup", "installer")
    candidates: List[str] = []
    for block_key in ("executable_artifacts",):
        for f in (inv.get(block_key) or {}).get("files") or []:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or "").lower()
            path = str(f.get("path") or "")
            if not path.lower().endswith(".exe"):
                continue
            if any(m in name for m in skip):
                continue
            candidates.append(path)
    if candidates:
        return candidates[0]
    rt = inv.get("runtime_artifacts") or {}
    for f in rt.get("executable_files") or []:
        if isinstance(f, dict) and f.get("path"):
            return str(f["path"])
    return ""


def get_submission_playtest_state(
    submission_id: int,
    grading_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Current playtest pass + criterion support for teacher UI."""
    session_dir, pass_dir = submission_playtest_dirs(submission_id)
    passes = list_playtest_passes(pass_dir=pass_dir)
    active = passes[0] if passes else None
    if not active and grading_snapshot:
        snap_pass = (grading_snapshot or {}).get("manual_playtest_pass") or {}
        if snap_pass.get("pass_id"):
            active = load_playtest_pass(str(snap_pass["pass_id"]), pass_dir=pass_dir) or snap_pass

    inv = (grading_snapshot or {}).get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    support = evaluate_operational_support(obs, inv)
    spec = load_spec()
    has_exe = _has_executable_artifacts(inv)
    l4_completed = obs.get("status") == "completed"
    session_id = runtime_session_id_from_snapshot(grading_snapshot)

    return {
        "submission_id": submission_id,
        "runtime_session_id": session_id,
        "playtest_available": bool(session_id or l4_completed or has_exe),
        "game_executable_path": _primary_game_executable_path(inv),
        "l4_gated": obs.get("status") == "gated",
        "governance_gate_reason": obs.get("reason") or obs.get("gate_ar"),
        "active_pass": active,
        "pass_count": len(passes),
        "spec_invariant_ar": spec.get("invariant_ar"),
        "runtime_criterion_support": support,
        "human_playtest_verified": bool(
            obs.get("human_playtest_verified")
            or (active or {}).get("playtest_status") == "complete_visual"
        ),
        "guardrail_note_ar": (
            "Playtest بشري يسجّل phenomenology فقط — لا يمنح Achieved تلقائياً في قاعدة البيانات. "
            "راجع C.P5/C.P6 يدوياً قبل تأكيد الدرجة."
        ),
    }


def start_submission_playtest(
    submission_id: int,
    *,
    student_name: str = "",
    grading_snapshot: Optional[Dict[str, Any]] = None,
    pass_mode: str = "visual_human",
) -> Dict[str, Any]:
    session_dir, pass_dir = submission_playtest_dirs(submission_id)
    parent_session_id = runtime_session_id_from_snapshot(grading_snapshot)
    if not parent_session_id:
        parent_session_id = f"ros_sub_{submission_id}"

    inv = (grading_snapshot or {}).get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    ensure_runtime_session_file(
        parent_session_id,
        session_dir=session_dir,
        submission_id=submission_id,
        student_label=student_name,
        artifact_paths=[_artifact_path_from_snapshot(grading_snapshot)] if _artifact_path_from_snapshot(grading_snapshot) else [],
        sandbox_snapshot=obs,
    )

    record = create_playtest_pass(
        parent_session_id,
        student_label=student_name,
        artifact_path=_artifact_path_from_snapshot(grading_snapshot),
        pass_mode=pass_mode,
        session_dir=session_dir,
        pass_dir=pass_dir,
        create_parent_if_missing=True,
        submission_id=submission_id,
    )
    save_playtest_pass(record, pass_dir=pass_dir)
    return record


def record_submission_playtest_observation(
    submission_id: int,
    pass_id: str,
    test_id: str,
    *,
    observed_en: str,
    status: str = "observed",
) -> Dict[str, Any]:
    _, pass_dir = submission_playtest_dirs(submission_id)
    record = load_playtest_pass(pass_id, pass_dir=pass_dir)
    if not record:
        raise FileNotFoundError(f"playtest pass not found: {pass_id}")
    record = record_test_observation(
        record,
        test_id,
        observed_en=observed_en,
        status=status,
    )
    save_playtest_pass(record, pass_dir=pass_dir)
    return record


def finalize_submission_playtest(
    submission_id: int,
    pass_id: str,
    grading_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    session_dir, pass_dir = submission_playtest_dirs(submission_id)
    record = load_playtest_pass(pass_id, pass_dir=pass_dir)
    if not record:
        raise FileNotFoundError(f"playtest pass not found: {pass_id}")

    record = finalize_playtest_pass(record, session_dir=session_dir)
    save_playtest_pass(record, pass_dir=pass_dir)

    parent_path = session_dir / f"{record['parent_session_id']}.json"
    iv_layer: Dict[str, Any] = {}
    if parent_path.is_file():
        try:
            parent = json.loads(parent_path.read_text(encoding="utf-8"))
            iv_layer = parent.get("interactive_verification_layer") or {}
        except (OSError, json.JSONDecodeError):
            iv_layer = {}

    updated_snapshot = merge_playtest_into_grading_snapshot(
        grading_snapshot or {},
        record,
        iv_layer,
        submission_id=submission_id,
    )
    return {
        "pass": record,
        "interactive_verification_layer": iv_layer,
        "grading_snapshot": updated_snapshot,
    }


def merge_playtest_into_grading_snapshot(
    snapshot: Dict[str, Any],
    pass_record: Dict[str, Any],
    iv_layer: Dict[str, Any],
    *,
    submission_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Attach L5 playtest fields and apply runtime adjudication to criteria_results when allowed."""
    snap = dict(snapshot or {})
    inv = dict(snap.get("artifact_inventory") or {})
    obs = dict(inv.get("runtime_observation_report") or {})

    complete_visual = pass_record.get("playtest_status") == "complete_visual"
    if complete_visual or iv_layer.get("interaction_visually_corroborated"):
        obs["human_playtest_verified"] = True
        obs["manual_playtest_verified"] = True
        obs["interaction_visually_corroborated"] = bool(
            iv_layer.get("interaction_visually_corroborated") or complete_visual
        )
        obs["mechanics_interactively_observed"] = bool(
            iv_layer.get("mechanics_interactively_observed") or complete_visual
        )

    pass_summary = {
        "pass_id": pass_record.get("pass_id"),
        "pass_mode": pass_record.get("pass_mode"),
        "playtest_status": pass_record.get("playtest_status"),
        "submission_id": submission_id or pass_record.get("submission_id"),
        "parent_session_id": pass_record.get("parent_session_id"),
        "interactive_phenomenology_descriptors": pass_record.get(
            "interactive_phenomenology_descriptors"
        ) or [],
        "tests_completed": sum(
            1 for t in (pass_record.get("tests") or []) if t.get("status") != "pending"
        ),
        "tests_total": len(pass_record.get("tests") or []),
        "finalized_at": pass_record.get("logged_at"),
        "assigns_legitimacy": False,
        "assigns_rubric_inference": False,
    }
    obs["manual_playtest_pass"] = pass_summary
    inv["runtime_observation_report"] = obs
    inv["manual_playtest_pass"] = pass_summary
    inv["runtime_criterion_support"] = evaluate_operational_support(obs, inv)
    # Ensure exe remains discoverable for L5 adjudication under gated L4
    if not (inv.get("executable_artifacts") or {}).get("files") and submission_id:
        try:
            from app.evidence_completeness_gate import expand_submission_paths

            primary = str(
                (snap.get("file_path") or snap.get("student_file_path") or "")
            ).strip()
            expanded = expand_submission_paths([primary] if primary else [], primary_path=primary)
            for p in expanded:
                if p.lower().endswith(".exe") and "unitycrashhandler" not in p.lower():
                    inv.setdefault("executable_artifacts", {}).setdefault("files", []).append(
                        {"path": p, "name": p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]}
                    )
                    inv["executable_artifacts"]["count"] = len(
                        inv["executable_artifacts"]["files"]
                    )
                    inv.setdefault("runtime_artifacts", {})["executables_detected"] = True
                    break
        except Exception:
            pass
    snap["artifact_inventory"] = inv
    snap["manual_playtest_pass"] = pass_summary
    snap["interactive_verification_layer"] = iv_layer
    snap["runtime_criterion_support"] = inv["runtime_criterion_support"]
    snap["l5_human_playtest"] = {
        "status": pass_record.get("playtest_status"),
        "verified": bool(obs.get("human_playtest_verified")),
        "note_ar": (
            "L5 playtest مُسجّل — advisory support فقط؛ القرار النهائي للمعلم."
        ),
    }
    if snap.get("criteria_results"):
        try:
            from app.runtime_criterion_mapping import apply_runtime_criterion_adjudication

            apply_runtime_criterion_adjudication(
                snap,
                observation=obs,
                inventory=inv,
            )
        except Exception:
            pass
    return snap
