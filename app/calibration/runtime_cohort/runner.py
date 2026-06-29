"""
STEP 3 — Real Runtime Cohort runner.

Measures operational reliability on real submissions and path fixtures:
  - runtime launch / freeze / crash
  - evidence completeness
  - deterministic replay stability (N trials on same snapshot)
  - AI vs human divergence (when human labels exist)
  - runtime reality (sandbox ran vs files-only detection)

Read-only — does not modify grades or governance state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.evidence_completeness_gate import expand_submission_paths, resolve_student_submission_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_snapshot(submission) -> Optional[Dict[str, Any]]:
    raw = getattr(submission, "grading_snapshot_json", None)
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _paths_from_snapshot(snap: Optional[Dict[str, Any]]) -> List[str]:
    if not snap:
        return []
    inv = snap.get("artifact_inventory") or {}
    paths: List[str] = []
    exe_block = inv.get("executable_artifacts") or {}
    for row in exe_block.get("files") or []:
        if isinstance(row, dict) and row.get("path"):
            paths.append(str(row["path"]))
    for row in inv.get("source_files") or []:
        if isinstance(row, dict) and row.get("path"):
            paths.append(str(row["path"]))
        elif isinstance(row, str):
            paths.append(row)
    return [p for p in paths if Path(p).exists()]


def _paths_from_fallback_root(root: Path) -> List[str]:
    if not root.exists():
        return []
    skip = {"monobleedingedge", "library", "temp", "obj", "bin"}
    paths: List[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part.lower() in skip for part in p.relative_to(root).parts):
            continue
        ext = p.suffix.lower()
        if ext in {".cs", ".exe", ".apk", ".pck", ".py", ".html", ".js", ".gd", ".gml"}:
            paths.append(str(p.resolve()))
    if not paths:
        return []
    primary = paths[0]
    for p in paths:
        if p.lower().endswith(".exe") and "unitycrashhandler" not in p.lower():
            primary = p
            break
    return expand_submission_paths(paths, primary_path=primary)


def _collect_paths_from_submission(
    submission,
    snap: Optional[Dict[str, Any]] = None,
    fallback_root: str = "",
) -> List[str]:
    root = resolve_student_submission_root(
        str(getattr(submission, "submission_file_path", "") or ""),
        student_name=str(getattr(submission, "student_name", "") or ""),
    )
    paths: List[str] = []
    if root and root.exists():
        skip = {"monobleedingedge", "library", "temp", "obj", "bin"}
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part.lower() in skip for part in p.relative_to(root).parts):
                continue
            ext = p.suffix.lower()
            if ext in {".cs", ".exe", ".apk", ".pck", ".py", ".html", ".js", ".gd", ".gml"}:
                paths.append(str(p.resolve()))
    if paths:
        primary = paths[0]
        for p in paths:
            if p.lower().endswith(".exe"):
                primary = p
                break
        return expand_submission_paths(
            paths,
            primary_path=primary,
            student_name=str(getattr(submission, "student_name", "") or ""),
        )
    if fallback_root:
        fb = _paths_from_fallback_root(Path(fallback_root))
        if fb:
            return fb
    return _paths_from_snapshot(snap)


def _collect_paths_from_fixture(root: Path, primary_name: str) -> List[str]:
    if not root.exists():
        return []
    primary = root / primary_name
    if not primary.exists():
        files = sorted(root.rglob("*"))
        files = [f for f in files if f.is_file()]
        if not files:
            return []
        primary = files[0]
    return sorted({str(p.resolve()) for p in root.rglob("*") if p.is_file()})


def run_replay_stability_trials(
    snap: Dict[str, Any],
    *,
    trials: int = 3,
    graded_at: Optional[str] = None,
) -> Dict[str, Any]:
    from app.academic_event_replay import build_academic_timeline_replay
    from app.deterministic_replay_engine import verify_deterministic_replay

    timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
    events = timeline.get("events") or []
    trial_results: List[Dict[str, Any]] = []
    for _ in range(max(1, trials)):
        v = verify_deterministic_replay(events, snap)
        trial_results.append(
            {
                "reconstructed_state_hash": v.get("reconstructed_state_hash"),
                "replay_verified": bool(v.get("replay_verified")),
                "semantic_replay_verified": bool(v.get("semantic_replay_verified")),
                "protected_digest_match": bool(v.get("protected_digest_match")),
                "grade_level": (v.get("state_summary") or {}).get("grade_level"),
            }
        )
    hashes = [t["reconstructed_state_hash"] for t in trial_results]
    unique_hashes = len({h for h in hashes if h})
    hash_stable = unique_hashes <= 1
    verification_stable = all(t["replay_verified"] for t in trial_results)
    semantic_stable = all(t["semantic_replay_verified"] for t in trial_results)
    return {
        "trials": trials,
        "hash_stable": hash_stable,
        "verification_stable": verification_stable,
        "semantic_stable": semantic_stable,
        "stable": hash_stable,
        "unique_state_hashes": unique_hashes,
        "trial_results": trial_results,
        "events_count": len(events),
        "interpretation_ar": (
            "إعادة التشغيل حتمية — نفس hash"
            if hash_stable and verification_stable
            else (
                "hash ثابت لكن verification فشل — drift في snapshot digest"
                if hash_stable and not verification_stable
                else "hash غير مستقر — replay reducer غير حتمي"
            )
        ),
    }


def probe_runtime(
    paths: List[str],
    *,
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    student_name: str = "",
) -> Dict[str, Any]:
    from app.runtime.sandbox_engine import detect_platform, run_sandbox_observation
    from app.runtime.validation_engine import (
        detect_crash,
        detect_freeze,
        validate_runtime_observation,
    )

    if not paths:
        return {
            "runtime_launch": "no_paths",
            "platform": "unknown",
            "sandbox_status": "skipped",
            "validation": {},
            "freeze_detection": {},
            "crash_detection": {},
            "sandbox_logs_captured": False,
        }

    platform = detect_platform(Path(paths[0]))
    obs = run_sandbox_observation(
        paths,
        submission_id=submission_id,
        batch_id=batch_id,
        student_name=student_name,
        enable_smoke_test=True,
    )
    validation = validate_runtime_observation(obs)
    freeze = detect_freeze(obs)
    crash = detect_crash(obs)
    status = str(obs.get("status") or "unknown")
    launch_ok = status in ("completed", "partial")

    return {
        "runtime_launch": "success" if launch_ok else ("gated" if status == "gated" else "fail"),
        "platform": platform,
        "sandbox_status": status,
        "functional_smoke_pass": validation.get("functional_smoke_pass"),
        "validation_status": validation.get("status"),
        "freeze_detection": {
            "pass": not freeze.get("freeze_suspected"),
            **freeze,
        },
        "crash_detection": {
            "detected": bool(crash.get("crash_detected")),
            **crash,
        },
        "runtime_duration_seconds": obs.get("runtime_duration_seconds"),
        "screenshot_count": len(obs.get("runtime_screenshots") or []),
        "sandbox_logs_captured": bool(obs.get("logs") or obs.get("stdout") or obs.get("stderr")),
        "observation_summary": {
            k: obs.get(k)
            for k in ("reason", "platform", "artifacts_observed", "smoke_test")
            if obs.get(k) is not None
        },
    }


def _extract_evidence_metrics(snap: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not snap:
        return {"available": False}
    gate = snap.get("evidence_completeness_gate") or {}
    inv = snap.get("artifact_inventory") or {}
    ror = inv.get("runtime_observation_report") or {}
    return {
        "available": True,
        "has_gaps": bool(gate.get("has_gaps")),
        "missing_artifacts": gate.get("missing_artifacts") or [],
        "completeness_score": gate.get("completeness_score"),
        "runtime_evidence_level": inv.get("runtime_evidence_level"),
        "executable_count": len(inv.get("executable_artifacts") or []),
        "source_file_count": len(inv.get("source_files") or []),
        "document_count": len(inv.get("documents") or []),
        "snapshot_runtime_status": ror.get("status"),
    }


def _extract_ai_grade(submission, snap: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    summary = getattr(submission, "summary", None) if submission else None
    grade = {
        "available": bool(summary or snap),
        "grade_level": getattr(summary, "grade_level", None) if summary else snap.get("grade_level") if snap else None,
        "percentage": getattr(summary, "percentage", None) if summary else snap.get("percentage") if snap else None,
        "total_score": getattr(summary, "total_score", None) if summary else snap.get("total_score") if snap else None,
        "max_score": getattr(summary, "max_score", None) if summary else snap.get("max_score") if snap else None,
    }
    if snap:
        achieved = [
            cr.get("criteria_level")
            for cr in (snap.get("criteria_results") or [])
            if isinstance(cr, dict) and cr.get("achieved")
        ]
        grade["achieved_criteria"] = achieved
        grade["achieved_count"] = len(achieved)
    return grade


def _load_human_labels(
    submission_id: Optional[int],
    labels_path: Optional[Path],
) -> Dict[str, Any]:
    if not submission_id or not labels_path or not labels_path.exists():
        return {"available": False}
    data = _load_json(labels_path)
    for row in data.get("records") or []:
        if int(row.get("submission_id") or 0) == submission_id:
            criteria = row.get("criteria") or []
            has_criteria = bool(criteria)
            if isinstance(criteria, dict):
                has_criteria = any(
                    isinstance(v, dict) and v.get("decision") is not None for v in criteria.values()
                )
            overall = row.get("overall_grade") or row.get("overall_grade_level")
            return {
                "available": bool(overall or has_criteria),
                "overall_grade_level": overall,
                "overall_percentage": row.get("overall_percentage"),
                "criteria": criteria,
                "notes_ar": row.get("overall_grade_notes") or row.get("notes_ar"),
                "reviewer": row.get("reviewer"),
            }
    return {"available": False, "reason": "no_label_row"}


def _human_ai_divergence(
    human: Dict[str, Any],
    ai: Dict[str, Any],
) -> Dict[str, Any]:
    if not human.get("available") or not ai.get("available"):
        return {"computed": False, "reason": "missing_human_or_ai"}
    h = human.get("overall_grade_level")
    a = ai.get("grade_level")
    if h is None and not human.get("criteria"):
        return {"computed": False, "reason": "human_grade_not_filled"}
    diverged = h is not None and a is not None and str(h).upper() != str(a).upper()
    return {
        "computed": True,
        "human_grade_level": h,
        "ai_grade_level": a,
        "diverged": diverged,
        "divergence_type": "grade_level_mismatch" if diverged else "aligned",
    }


def _runtime_reality(snap: Optional[Dict[str, Any]], runtime_probe: Dict[str, Any]) -> Dict[str, Any]:
    inv = (snap or {}).get("artifact_inventory") or {}
    ror = inv.get("runtime_observation_report") or {}
    snap_status = str(ror.get("status") or "")
    probe_status = str(runtime_probe.get("sandbox_status") or "")
    sandbox_ran = probe_status in ("completed", "partial") or snap_status in ("completed", "partial")
    has_exe = bool(inv.get("executable_artifacts")) or runtime_probe.get("platform") in (
        "unity",
        "exe",
        "apk",
        "godot",
    )
    files_only = has_exe and not sandbox_ran
    return {
        "executable_detected": has_exe,
        "sandbox_actually_ran": sandbox_ran,
        "files_only_detection": files_only,
        "runtime_evidence_level": inv.get("runtime_evidence_level"),
        "interpretation_ar": (
            "تشغيل فعلي في sandbox"
            if sandbox_ran
            else ("اكتشاف ملفات فقط — لم يُشغَّل" if has_exe else "لا runtime")
        ),
    }


def _ocr_metrics(snap: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not snap:
        return {"present": False}
    inv = snap.get("artifact_inventory") or {}
    vision = snap.get("vision_verification") or snap.get("interactive_verification_layer") or {}
    ocr_rows = []
    for key in ("screenshot_analyses", "analyses", "artifacts"):
        for row in vision.get(key) or []:
            if isinstance(row, dict) and row.get("ocr_char_count") is not None:
                ocr_rows.append(row)
    useful = any(r.get("ocr_has_ui_text") for r in ocr_rows)
    noise = bool(ocr_rows) and not useful
    return {
        "present": bool(ocr_rows),
        "ocr_artifact_count": len(ocr_rows),
        "useful": useful if ocr_rows else None,
        "noise_suspected": noise,
        "runtime_screenshot_count": len(inv.get("runtime_screenshots") or []),
    }


def evaluate_db_entry(
    submission,
    *,
    replay_trials: int = 3,
    run_runtime: bool = True,
    human_labels_path: Optional[Path] = None,
    fallback_root: str = "",
) -> Dict[str, Any]:
    snap = _load_snapshot(submission)
    paths = (
        _collect_paths_from_submission(submission, snap, fallback_root=fallback_root)
        if run_runtime
        else []
    )
    graded_at = None
    if getattr(submission, "summary", None) and submission.summary.graded_at:
        graded_at = submission.summary.graded_at.isoformat() + "Z"

    runtime_probe = (
        probe_runtime(
            paths,
            submission_id=int(submission.id),
            batch_id=getattr(submission, "batch_id", None),
            student_name=str(getattr(submission, "student_name", "") or ""),
        )
        if run_runtime
        else {"runtime_launch": "skipped", "sandbox_status": "skipped"}
    )

    replay = run_replay_stability_trials(snap, trials=replay_trials, graded_at=graded_at) if snap else {
        "trials": replay_trials,
        "stable": None,
        "reason": "no_snapshot",
    }

    disparity = None
    if snap:
        from app.replay_disparity_analytics import analyze_submission_replay_disparity

        disparity = analyze_submission_replay_disparity(submission, graded_at=graded_at)

    ai_grade = _extract_ai_grade(submission, snap)
    human = _load_human_labels(int(submission.id), human_labels_path)
    screenshot_count = runtime_probe.get("screenshot_count")

    return {
        "source_type": "db",
        "submission_id": int(submission.id),
        "student_name": getattr(submission, "student_name", "") or "",
        "paths_resolved": len(paths),
        "path_source": (
            "fallback_root"
            if fallback_root and paths
            else ("db_uploads" if paths else "none")
        ),
        "batch_id": getattr(submission, "batch_id", None),
        "metrics": {
            "runtime_launch": runtime_probe.get("runtime_launch"),
            "freeze_detection": runtime_probe.get("freeze_detection"),
            "crash_detection": runtime_probe.get("crash_detection"),
            "evidence_extraction": _extract_evidence_metrics(snap),
            "ai_grade": ai_grade,
            "human_grade": human,
            "ai_vs_human": _human_ai_divergence(human, ai_grade),
            "replay_reproducibility": replay,
            "runtime_reality": _runtime_reality(snap, runtime_probe),
            "sandbox_logs": {
                "captured": runtime_probe.get("sandbox_logs_captured"),
                "status": runtime_probe.get("sandbox_status"),
            },
            "screenshot_evidence": {
                "count": screenshot_count if isinstance(screenshot_count, int) else 0,
                "valid": isinstance(screenshot_count, int) and screenshot_count > 0,
            },
            "ocr_usefulness": _ocr_metrics(snap),
            "runtime_probe": runtime_probe,
            "replay_disparity": {
                "replay_unstable": (disparity or {}).get("replay_stability", {}).get("replay_unstable"),
                "replay_cohorts": (disparity or {}).get("replay_cohorts"),
            }
            if disparity
            else None,
        },
    }


def evaluate_path_entry(
    entry: Dict[str, Any],
    project_root: Path,
    *,
    replay_trials: int = 3,
    run_runtime: bool = True,
) -> Dict[str, Any]:
    src = entry.get("source") or {}
    root = project_root / str(src.get("root") or "")
    primary = str(src.get("primary") or "")
    paths = _collect_paths_from_fixture(root, primary) if run_runtime else []

    runtime_probe = (
        probe_runtime(paths, student_name=entry.get("slot_id", ""))
        if run_runtime
        else {"runtime_launch": "skipped", "sandbox_status": "skipped"}
    )
    screenshot_count = runtime_probe.get("screenshot_count")

    return {
        "source_type": "path",
        "slot_id": entry.get("slot_id"),
        "platform": entry.get("platform"),
        "tier": entry.get("tier"),
        "label_ar": entry.get("label_ar"),
        "fixture_root": str(root),
        "metrics": {
            "runtime_launch": runtime_probe.get("runtime_launch"),
            "freeze_detection": runtime_probe.get("freeze_detection"),
            "crash_detection": runtime_probe.get("crash_detection"),
            "evidence_extraction": {"available": False, "reason": "fixture_only"},
            "ai_grade": {"available": False},
            "human_grade": {"available": False},
            "ai_vs_human": {"computed": False, "reason": "fixture_only"},
            "replay_reproducibility": {"stable": None, "reason": "no_graded_snapshot"},
            "runtime_reality": _runtime_reality(None, runtime_probe),
            "sandbox_logs": {
                "captured": runtime_probe.get("sandbox_logs_captured"),
                "status": runtime_probe.get("sandbox_status"),
            },
            "screenshot_evidence": {
                "count": screenshot_count if isinstance(screenshot_count, int) else 0,
                "valid": isinstance(screenshot_count, int) and screenshot_count > 0,
            },
            "ocr_usefulness": {"present": False},
            "runtime_probe": runtime_probe,
        },
    }


def _cohort_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    replay_stable = []
    runtime_launched = []
    files_only = []
    human_diverged = []
    for row in results:
        m = row.get("metrics") or {}
        rep = m.get("replay_reproducibility") or {}
        if rep.get("hash_stable") is True:
            replay_stable.append(row.get("slot_id") or row.get("submission_id"))
        elif rep.get("stable") is False:
            pass
        rr = m.get("runtime_reality") or {}
        if rr.get("sandbox_actually_ran"):
            runtime_launched.append(row.get("slot_id") or row.get("submission_id"))
        if rr.get("files_only_detection"):
            files_only.append(row.get("slot_id") or row.get("submission_id"))
        div = m.get("ai_vs_human") or {}
        if div.get("diverged"):
            human_diverged.append(row.get("slot_id") or row.get("submission_id"))

    unstable = [
        row.get("slot_id") or row.get("submission_id")
        for row in results
        if (row.get("metrics") or {}).get("replay_reproducibility", {}).get("hash_stable") is False
    ]
    verification_failures = [
        row.get("slot_id") or row.get("submission_id")
        for row in results
        if (row.get("metrics") or {}).get("replay_reproducibility", {}).get("hash_stable") is True
        and (row.get("metrics") or {}).get("replay_reproducibility", {}).get("verification_stable") is False
    ]

    return {
        "deterministic_replay_stable_count": len(replay_stable),
        "deterministic_replay_unstable": unstable,
        "replay_hash_stable_verification_failed": verification_failures,
        "runtime_actually_launched": runtime_launched,
        "files_only_detection": files_only,
        "ai_human_divergence": human_diverged,
        "priority_flags": {
            "replay_hash_unstable": bool(unstable),
            "replay_verification_mismatch": bool(verification_failures),
            "runtime_not_executed": bool(files_only),
            "human_labels_missing": all(
                not (row.get("metrics") or {}).get("human_grade", {}).get("available")
                for row in results
                if row.get("source_type") == "db"
            ),
        },
    }


def build_cohort_report(
    results: List[Dict[str, Any]],
    *,
    cohort_id: str,
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "report_type": "runtime_cohort_v1",
        "cohort_id": cohort_id,
        "generated_at": _utc_now(),
        "config_path": config_path,
        "entry_count": len(results),
        "summary": _cohort_summary(results),
        "entries": results,
    }


def run_cohort(
    config_path: Path,
    project_root: Path,
    *,
    run_runtime: bool = True,
    human_labels_path: Optional[Path] = None,
    submission_ids: Optional[List[int]] = None,
    fixtures_only: bool = False,
) -> Dict[str, Any]:
    from app.database import SessionLocal
    from app.models import Submission

    cfg = _load_json(config_path)
    replay_trials = int(cfg.get("replay_trials") or 3)
    results: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        for entry in cfg.get("entries") or []:
            src = entry.get("source") or {}
            if src.get("type") == "db":
                if fixtures_only:
                    continue
                sid = int(src.get("submission_id") or 0)
                if submission_ids and sid not in submission_ids:
                    continue
                sub = db.query(Submission).filter(Submission.id == sid).first()
                if not sub:
                    results.append(
                        {
                            "slot_id": entry.get("slot_id"),
                            "source_type": "db",
                            "submission_id": sid,
                            "error": "submission_not_found",
                        }
                    )
                    continue
                row = evaluate_db_entry(
                    sub,
                    replay_trials=replay_trials,
                    run_runtime=run_runtime,
                    human_labels_path=human_labels_path,
                    fallback_root=str(src.get("fallback_root") or ""),
                )
                row["slot_id"] = entry.get("slot_id")
                row["platform"] = entry.get("platform")
                row["tier"] = entry.get("tier")
                row["label_ar"] = entry.get("label_ar")
                results.append(row)
            elif src.get("type") == "path":
                if submission_ids:
                    continue
                row = evaluate_path_entry(
                    entry,
                    project_root,
                    replay_trials=replay_trials,
                    run_runtime=run_runtime,
                )
                results.append(row)
    finally:
        db.close()

    return build_cohort_report(
        results,
        cohort_id=str(cfg.get("cohort_id") or "runtime_cohort"),
        config_path=str(config_path),
    )


def run_cohort_for_batch(
    batch_id: int,
    *,
    run_runtime: bool = True,
    replay_trials: int = 3,
    human_labels_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Runtime coverage mapping for all submissions in a batch (read-only)."""
    from app.database import SessionLocal
    from app.models import Submission

    db = SessionLocal()
    results: List[Dict[str, Any]] = []
    try:
        subs = (
            db.query(Submission)
            .filter(Submission.batch_id == batch_id)
            .order_by(Submission.id)
            .all()
        )
        for sub in subs:
            row = evaluate_db_entry(
                sub,
                replay_trials=replay_trials,
                run_runtime=run_runtime,
                human_labels_path=human_labels_path,
            )
            row["slot_id"] = f"batch{batch_id}_sub_{sub.id}"
            row["platform"] = "batch"
            row["tier"] = "pilot"
            row["label_ar"] = str(getattr(sub, "student_name", "") or "")
            results.append(row)
    finally:
        db.close()

    report = build_cohort_report(
        results,
        cohort_id=f"batch_{batch_id}_runtime_coverage",
    )
    report["batch_id"] = batch_id
    report["purpose_ar"] = "Runtime Coverage Mapping — read-only, no grade changes"
    return report
