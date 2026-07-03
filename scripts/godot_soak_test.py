"""Godot runtime soak matrix — records per-run fields for closeout sign-off.

Run in **foreground** only — full matrix (~15–20 min per submission_50 run).
Background harness may abort long processes silently.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("WHATSAPP_AUTO_START", "false")
os.environ.setdefault("PRO_FAST_PATH", "0")

HARNESS_VERSION = "godot_soak_harness_v2"
FIXTURES_PATH = ROOT / "scripts" / "godot_soak_fixtures.json"
REPORTS_DIR = ROOT / "reports"

_partial_report_state: dict[str, Any] = {}


def _load_fixtures() -> dict:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def _load_snapshot_gameplay_verification(result: dict) -> dict:
    """Read gv from replay snapshot — same truth source as runtime/runtime.json."""
    inv = result.get("artifact_inventory") or {}
    rt = inv.get("runtime_observation_report") or {}
    sid = str(rt.get("runtime_session_id") or "")
    if not sid:
        return {}
    snapshots_root = ROOT / "uploads" / "replay_snapshots"
    if not snapshots_root.is_dir():
        return {}
    matches = sorted(snapshots_root.glob(f"**/{sid}/runtime/runtime.json"))
    if not matches:
        matches = sorted(snapshots_root.glob(f"**/*{sid[:8]}*/runtime/runtime.json"))
    if not matches:
        return {}
    try:
        data = json.loads(matches[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    gv = data.get("gameplay_verification")
    return dict(gv) if isinstance(gv, dict) and gv else {}


def _gameplay_fields_from_result(result: dict) -> tuple[dict, dict]:
    from app.gameplay_verifier import build_gameplay_verification_summary

    inv = result.get("artifact_inventory") or {}
    rt = inv.get("runtime_observation_report") or {}
    gv = result.get("gameplay_verification")
    if not isinstance(gv, dict) or not gv:
        from app.gameplay_verifier import _gameplay_verification_blob

        gv = _gameplay_verification_blob(rt, inventory=inv, grading_result=result)
    inv_for_summary = {**inv, "gameplay_verification": gv}
    summary = build_gameplay_verification_summary(
        rt,
        inventory=inv_for_summary,
        grading_result={**result, "gameplay_verification": gv},
    )
    return gv or {}, summary


def _gameplay_fields_from_observation(obs: dict) -> tuple[dict, dict]:
    from app.gameplay_verifier import _gameplay_verification_blob, build_gameplay_verification_summary

    inv = {"gameplay_verification": obs.get("gameplay_verification")}
    gv = _gameplay_verification_blob(obs, inventory=inv)
    summary = build_gameplay_verification_summary(obs, inventory={"gameplay_verification": gv or obs.get("gameplay_verification")})
    return gv, summary


def _run_status(record: dict) -> str:
    if record.get("skipped"):
        return "skipped"
    if record.get("status") == "error":
        return "error"
    if record.get("blocking_bug"):
        return "blocking_bug"
    if record.get("correct"):
        return "pass"
    return "fail"


def _blocking_bug(record: dict, *, runtime_observed: bool = False) -> bool:
    if record.get("skipped") or record.get("status") == "error":
        return False
    if not runtime_observed and record.get("mode") != "full_grade":
        return record.get("gameplay_entered") is None and not record.get("failure_reason_code")
    if record.get("gameplay_entered") is None:
        return True
    if record.get("gameplay_entered") is False and not record.get("failure_reason_code"):
        return True
    return False


def _extract_run_record(
    result: dict,
    *,
    fixture_id: str,
    run_index: int,
    duration_ms: int,
) -> dict[str, Any]:
    gv, summary = _gameplay_fields_from_result(result)
    gate = summary.get("automated_l4_gate") or {}
    cp = gate.get("criterion_pass") or {}
    failure_code = gv.get("failure_reason_code") or summary.get("failure_reason_code")
    gameplay_entered = summary.get("gameplay_entered")
    if gameplay_entered is None:
        gameplay_entered = gv.get("gameplay_entered")
    rt = (result.get("artifact_inventory") or {}).get("runtime_observation_report") or {}
    runtime_observed = bool(rt.get("runtime_observed"))
    record = {
        "fixture_id": fixture_id,
        "run_index": run_index,
        "status": "ok",
        "mode": "full_grade",
        "gameplay_entered": gameplay_entered,
        "l4_level": summary.get("l4_level") or gv.get("l4_level") or gv.get("automated_l4_level"),
        "failure_reason_code": failure_code,
        "criterion_pass_p5": bool(cp.get("P5")),
        "criterion_pass_p6": bool(cp.get("P6")),
        "grade_level": result.get("grade_level"),
        "resolution_source": gv.get("_resolution_source"),
        "runtime_observed": runtime_observed,
        "duration_ms": duration_ms,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    record["correct"] = _is_correct_outcome(gameplay_entered, failure_code)
    record["blocking_bug"] = _blocking_bug(record, runtime_observed=runtime_observed)
    record["status"] = _run_status(record)
    return record


def _is_correct_outcome(gameplay_entered: Any, failure_code: Any) -> bool:
    if gameplay_entered is True:
        return failure_code in (None, "")
    if gameplay_entered is False:
        return bool(failure_code)
    return bool(failure_code)


def _observation_run_record(
    obs: dict,
    *,
    fixture_id: str,
    run_index: int,
    duration_ms: int,
) -> dict[str, Any]:
    gv, summary = _gameplay_fields_from_observation(obs)
    gate = summary.get("automated_l4_gate") or {}
    cp = gate.get("criterion_pass") or {}
    failure_code = gv.get("failure_reason_code") or summary.get("failure_reason_code")
    gameplay_entered = summary.get("gameplay_entered")
    if gameplay_entered is None:
        gameplay_entered = gv.get("gameplay_entered")
    p5 = bool(cp.get("P5"))
    p6 = bool(cp.get("P6"))
    runtime_observed = bool(obs.get("runtime_observed"))
    record = {
        "fixture_id": fixture_id,
        "run_index": run_index,
        "status": "ok",
        "mode": "runtime_only",
        "gameplay_entered": gameplay_entered,
        "l4_level": summary.get("l4_level") or gv.get("l4_level"),
        "failure_reason_code": failure_code,
        "criterion_pass_p5": p5,
        "criterion_pass_p6": p6,
        "grade_level": "P" if p5 and p6 else "U",
        "resolution_source": gv.get("_resolution_source"),
        "runtime_observed": runtime_observed,
        "duration_ms": duration_ms,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    record["correct"] = _is_correct_outcome(gameplay_entered, failure_code)
    record["blocking_bug"] = _blocking_bug(record, runtime_observed=runtime_observed)
    record["status"] = _run_status(record)
    return record


def _error_run_record(
    *,
    fixture_id: str,
    run_index: int,
    exc: BaseException,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "run_index": run_index,
        "status": "error",
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(),
        "gameplay_entered": None,
        "failure_reason_code": None,
        "correct": False,
        "blocking_bug": False,
        "duration_ms": duration_ms,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


async def _grade_submission(fixture: dict, run_index: int) -> dict[str, Any]:
    from app.batch_grader import grade_batch_async
    from app.btec_criteria_governance import ensure_clean_grading_result_feedback
    from app.criteria_result_finalizer import finalize_grading_criteria_results
    from app.database import SessionLocal
    from app.models import Assignment, GradingCriteria, Submission

    sub_id = int(fixture["submission_id"])
    db = SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.id == sub_id).first()
        if not sub:
            raise RuntimeError(f"submission {sub_id} not found")
        assignment = db.query(Assignment).filter(Assignment.id == sub.assignment_id).first()
        if not assignment:
            raise RuntimeError(f"assignment for submission {sub_id} not found")
        criteria = (
            db.query(GradingCriteria)
            .filter(GradingCriteria.assignment_id == sub.assignment_id)
            .all()
        )
        grading_criteria = [
            {
                "criteria_level": c.criteria_level,
                "criteria_name": c.criteria_name,
                "criteria_description": c.criteria_description,
                "max_score": c.weight,
            }
            for c in criteria
        ]
        ref = json.loads(assignment.reference_solution_json or "{}")
        snap = json.loads(str(sub.grading_snapshot_json or "{}"))
        paths = list(snap.get("submission_paths") or snap.get("intake_relative_paths") or [])
        if sub.submission_file_path:
            paths.append(str(sub.submission_file_path))
            paths.append(str(Path(str(sub.submission_file_path)).parent))
        paths = sorted({str(p) for p in paths if p and Path(str(p)).is_file()}, key=str.lower)
        if not paths:
            root = Path("uploads/students")
            folder = root / "bx72" / "Ahmad Bakr Hatem Abu Shaira TF(77644)  هدف (ب+ج)"
            if folder.is_dir():
                paths = sorted({str(p) for p in folder.rglob("*") if p.is_file()}, key=str.lower)
        primary = str(sub.submission_file_path or (paths[0] if paths else ""))
        if paths and (not primary or not Path(primary).is_file()):
            primary = next(
                (p for p in paths if p.lower().endswith((".docx", ".pdf", ".exe"))),
                paths[0],
            )
        has_exe = any(str(p).lower().endswith(".exe") for p in paths)
        has_code = any(
            str(p).lower().endswith((".gd", ".gml", ".cs", ".tscn")) for p in paths
        )
        student_info = {
            "name": sub.student_name,
            "path": primary,
            "email": "",
            "student_id": "",
            "submission_paths": paths,
            "submission_id": sub.id,
            "batch_id": sub.batch_id,
            "has_code_files": has_code,
            "has_executable_artifacts": has_exe,
        }
    finally:
        db.close()

    results = await grade_batch_async(
        [student_info],
        ref,
        grading_criteria,
        skip_grading_cache=True,
        grading_mode="deep",
        max_workers=1,
    )
    result = results[0] if results else {}
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "grade failed")
    inv = dict(result.get("artifact_inventory") or {})
    gv = result.get("gameplay_verification")
    if isinstance(gv, dict) and gv:
        inv["gameplay_verification"] = gv
    finalize_grading_criteria_results(result, artifact_inventory=inv)
    ensure_clean_grading_result_feedback(result)
    from app.gameplay_verifier import (
        _authoritative_gv_richness,
        resolve_authoritative_gameplay_verification,
    )

    synced = resolve_authoritative_gameplay_verification(
        artifact_inventory=inv,
        grading_result=result,
    )
    snapshot_gv = _load_snapshot_gameplay_verification(result)
    if _authoritative_gv_richness(snapshot_gv) > _authoritative_gv_richness(synced):
        synced = snapshot_gv
    if synced:
        result["gameplay_verification"] = synced
        inv["gameplay_verification"] = synced
        rt = inv.get("runtime_observation_report") or {}
        if isinstance(rt, dict):
            rt = dict(rt)
            rt["gameplay_verification"] = synced
            inv["runtime_observation_report"] = rt
        result["artifact_inventory"] = inv
    return result


def _run_corpus_fixture(fixture: dict) -> dict[str, Any]:
    from app.runtime_observation_sandbox import observe_runtime_artifacts

    exe = ROOT / str(fixture["path"])
    if not exe.is_file():
        raise FileNotFoundError(f"corpus exe missing: {exe}")
    return observe_runtime_artifacts([str(exe)], grading_mode="deep", enable_smoke_test=True)


def _evaluate_matrix(runs: list[dict], *, submission_50_runs: list[dict]) -> dict[str, Any]:
    active = [r for r in runs if not r.get("skipped")]
    correct = sum(1 for r in active if r.get("correct"))
    total = len(active)
    failed_without_code = [
        r for r in active if r.get("gameplay_entered") is False and not r.get("failure_reason_code")
    ]
    blocking_bugs = [r for r in active if r.get("blocking_bug")]
    errors = [r for r in active if r.get("status") == "error"]
    sub50 = submission_50_runs
    sub50_stable = False
    if len(sub50) >= 3:
        grades = {str(r.get("grade_level") or "") for r in sub50}
        codes = {str(r.get("failure_reason_code") or "") for r in sub50}
        all_pass = grades == {"P"} and all(r.get("gameplay_entered") is True for r in sub50)
        all_same_fail = len(codes) == 1 and codes != {""} and all(
            r.get("gameplay_entered") is not True for r in sub50
        )
        sub50_stable = all_pass or all_same_fail
    min_correct = max(1, int(total * 8 / 9)) if total else 0
    passed = (
        total >= 1
        and correct >= min_correct
        and not failed_without_code
        and not blocking_bugs
        and not errors
        and (not sub50 or len(sub50) < 3 or sub50_stable)
    )
    return {
        "total_runs": total,
        "correct_runs": correct,
        "min_correct_required": min_correct,
        "submission_50_stable": sub50_stable,
        "failed_without_failure_code": len(failed_without_code),
        "blocking_bug_count": len(blocking_bugs),
        "error_count": len(errors),
        "passed": passed,
    }


def _write_report(payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"godot_soak_{stamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = REPORTS_DIR / "godot_soak_latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _flush_log(log_file: Optional[Path], message: str) -> None:
    print(message, flush=True)
    if log_file:
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(message + "\n")


async def run_matrix(*, runs_per_fixture: int, log_file: Optional[Path] = None) -> Path:
    cfg = _load_fixtures()
    all_runs: list[dict] = []
    submission_50_runs: list[dict] = []
    started = time.monotonic()

    _partial_report_state["runs"] = all_runs
    _partial_report_state["runs_per_fixture"] = runs_per_fixture

    for fixture in cfg.get("fixtures") or []:
        fid = fixture.get("id") or "unknown"
        if fixture.get("pending"):
            for i in range(1, runs_per_fixture + 1):
                all_runs.append(
                    {
                        "fixture_id": fid,
                        "run_index": i,
                        "skipped": True,
                        "status": "skipped",
                        "reason": fixture.get("notes") or "pending fixture",
                    }
                )
            continue
        kind = fixture.get("kind")
        for i in range(1, runs_per_fixture + 1):
            _flush_log(log_file, f"\n=== {fid} run {i}/{runs_per_fixture} ===")
            t0 = time.monotonic()
            record: dict[str, Any]
            try:
                if kind == "db_submission":
                    result = await _grade_submission(fixture, i)
                    record = _extract_run_record(
                        result,
                        fixture_id=fid,
                        run_index=i,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                elif kind == "corpus_exe":
                    obs = _run_corpus_fixture(fixture)
                    record = _observation_run_record(
                        obs,
                        fixture_id=fid,
                        run_index=i,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                else:
                    record = {
                        "fixture_id": fid,
                        "run_index": i,
                        "skipped": True,
                        "status": "skipped",
                        "reason": f"unsupported kind: {kind}",
                    }
            except Exception as exc:
                record = _error_run_record(
                    fixture_id=fid,
                    run_index=i,
                    exc=exc,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
                _flush_log(log_file, record.get("error") or str(exc))
                _flush_log(log_file, record.get("traceback") or "")

            _flush_log(log_file, json.dumps(record, ensure_ascii=False, indent=2))
            all_runs.append(record)
            if fid == "submission_50" and not record.get("skipped"):
                submission_50_runs.append(record)

    evaluation = _evaluate_matrix(all_runs, submission_50_runs=submission_50_runs)
    payload = {
        "harness_version": HARNESS_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "fixtures_file": str(FIXTURES_PATH),
        "runs_per_fixture": runs_per_fixture,
        "runs": all_runs,
        "evaluation": evaluation,
    }
    out_path = _write_report(payload)
    _partial_report_state["report_path"] = str(out_path)
    _flush_log(log_file, "\n=== SOAK EVALUATION ===")
    _flush_log(log_file, json.dumps(evaluation, ensure_ascii=False, indent=2))
    _flush_log(log_file, f"Report: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Godot runtime soak matrix")
    parser.add_argument("--runs", type=int, default=None, help="Runs per fixture (default from JSON)")
    parser.add_argument("--log-file", type=str, default=None, help="Optional log file path")
    args = parser.parse_args()
    cfg = _load_fixtures()
    runs = args.runs or int(cfg.get("runs_per_fixture") or 3)
    log_path = Path(args.log_file) if args.log_file else REPORTS_DIR / "godot_soak_latest.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    out: Optional[Path] = None
    try:
        out = asyncio.run(run_matrix(runs_per_fixture=runs, log_file=log_path))
    except Exception as exc:
        partial = {
            "harness_version": HARNESS_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "harness_crash",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "runs": _partial_report_state.get("runs") or [],
            "runs_per_fixture": _partial_report_state.get("runs_per_fixture"),
        }
        out = _write_report(partial)
        print(f"Harness crash — partial report: {out}", flush=True)
        raise SystemExit(1) from exc

    if out is None or not out.is_file():
        raise SystemExit("soak report was not written")

    data = json.loads(out.read_text(encoding="utf-8"))
    if not data.get("evaluation", {}).get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
