"""One-shot Godot exe trial before registering student_godot_2 in soak fixtures."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("WHATSAPP_AUTO_START", "false")
os.environ.setdefault("PRO_FAST_PATH", "0")

REPORTS_DIR = ROOT / "reports"
NETWORK_HINTS = ("connection", "network", "server", "login", "multiplayer")


def _slug_from_exe(exe_path: str) -> str:
    stem = Path(exe_path).stem.lower().replace(" ", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in stem).strip("_") or "trial"


def _relative_exe_path(exe: Path) -> str:
    try:
        return str(exe.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(exe).replace("\\", "/")


def _godot_retry_steps(gv: dict) -> list[str]:
    steps: list[str] = []
    for row in gv.get("godot_retry_attempts") or []:
        if isinstance(row, dict) and row.get("step"):
            steps.append(str(row["step"]))
    return steps


def _guess_profile(gv: dict, steps: list[str]) -> str:
    if any("nav_pass" in s for s in steps):
        return "simple_menu"
    if gv.get("gameplay_entered") is True or any("play_pass" in s for s in steps):
        return "direct_gameplay"
    return "unknown"


def _network_hints(exe_path: str) -> bool:
    low = exe_path.lower()
    return any(h in low for h in NETWORK_HINTS)


def _gates_passed(gv: dict, *, duration_ms: int) -> bool:
    entered = gv.get("gameplay_entered")
    code = gv.get("failure_reason_code")
    if entered is None:
        return False
    if entered is False and not code:
        return False
    if duration_ms >= 60_000:
        return False
    return True


def build_trial_report(
    obs: dict,
    *,
    exe_path: str,
    duration_ms: int,
    student_label: str = "ahmad hamtini",
) -> dict[str, Any]:
    from app.gameplay_verifier import resolve_authoritative_gameplay_verification

    gv = resolve_authoritative_gameplay_verification(
        artifact_inventory={"runtime_observation_report": obs},
        grading_result={"gameplay_verification": obs.get("gameplay_verification")},
    )
    if not gv and isinstance(obs.get("gameplay_verification"), dict):
        gv = dict(obs["gameplay_verification"])
    gv = gv or {}

    trace = obs.get("interaction_trace") if isinstance(obs.get("interaction_trace"), dict) else {}
    steps = _godot_retry_steps(gv)
    notes: list[str] = []
    pck = Path(exe_path).with_suffix(".pck")
    if not pck.is_file():
        notes.append(f"missing_pck:{pck.name}")

    failure_code = gv.get("failure_reason_code")
    if failure_code in ("", None):
        failure_code = None

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "exe_path": exe_path.replace("\\", "/"),
        "student_label": student_label,
        "duration_ms": duration_ms,
        "launch_ok": bool(obs.get("runtime_observed")) or bool(obs.get("runtime_screenshots")),
        "gameplay_entered": gv.get("gameplay_entered"),
        "failure_reason_code": failure_code,
        "l4_level": gv.get("l4_level") or gv.get("automated_l4_level"),
        "screenshot_count": len(obs.get("runtime_screenshots") or []),
        "godot_retry_steps": steps,
        "profile_guess": _guess_profile(gv, steps),
        "network_hints": _network_hints(exe_path),
        "gates_passed": _gates_passed(gv, duration_ms=duration_ms),
        "terminal_classify": gv.get("terminal_classify"),
        "interaction_errors": [str(e) for e in (trace.get("errors") or [])][:8],
        "notes": notes,
    }


def _report_score(report: dict) -> tuple:
    profile_rank = {"direct_gameplay": 2, "simple_menu": 1, "unknown": 0}
    errors = report.get("interaction_errors") or []
    capture_penalty = 1 if report.get("terminal_classify") == "capture_pipeline" else 0
    is_final = 1 if str(report.get("exe_path", "")).lower().endswith("final.exe") else 0
    return (
        1 if report.get("gates_passed") else 0,
        -len(errors),
        -capture_penalty,
        profile_rank.get(str(report.get("profile_guess") or "unknown"), 0),
        -int(report.get("duration_ms") or 0),
        is_final,
    )


def compare_trial_reports(reports: list[dict]) -> dict[str, Any]:
    if not reports:
        raise ValueError("no trial reports to compare")
    ranked = sorted(reports, key=_report_score, reverse=True)
    winner = dict(ranked[0])
    winner["compare_rank"] = 1
    winner["compare_reason"] = (
        "gates_passed and stability signals; tie-break prefers final.exe per spec §14.7"
    )
    return winner


def run_trial(exe: Path) -> dict[str, Any]:
    from app.runtime_observation_sandbox import observe_runtime_artifacts

    if not exe.is_file():
        raise FileNotFoundError(f"exe not found: {exe}")
    t0 = time.monotonic()
    obs = observe_runtime_artifacts(
        [str(exe.resolve())],
        grading_mode="deep",
        enable_smoke_test=True,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    return build_trial_report(
        obs,
        exe_path=_relative_exe_path(exe),
        duration_ms=duration_ms,
    )


def _write_report(report: dict, out_path: Path | None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        slug = _slug_from_exe(str(report.get("exe_path") or "trial"))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = REPORTS_DIR / f"godot_trial_{slug}_{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Godot single-exe trial runner")
    parser.add_argument("--exe", help="Path to Godot exe relative to project root or absolute")
    parser.add_argument("--compare", nargs=2, metavar="REPORT_A", help="Compare two trial JSON reports")
    parser.add_argument("--out", help="Output JSON path for trial report")
    args = parser.parse_args(argv)

    if args.compare:
        paths = [Path(p) for p in args.compare]
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
        winner = compare_trial_reports(reports)
        print(json.dumps(winner, ensure_ascii=False, indent=2))
        return 0

    if not args.exe:
        parser.error("--exe or --compare is required")

    exe = Path(args.exe)
    if not exe.is_file():
        exe = ROOT / args.exe
    report = run_trial(exe)
    out_path = _write_report(report, Path(args.out) if args.out else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
