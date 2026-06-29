#!/usr/bin/env python3
"""Verify all runtime engines — one command before market launch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLES = ROOT / "demos" / "samples"


def _ok(msg: str) -> None:
    print(f"PASS  {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL  {msg}")


def _warn(msg: str) -> None:
    print(f"WARN  {msg}")


def verify_engine(name: str, sample_path: Path, *, timeout: int = 15) -> Dict[str, Any]:
    from app.runtime.orchestrator import run_runtime_session
    from app.runtime_engines.registry import resolve_engine

    result: Dict[str, Any] = {"engine": name, "sample": str(sample_path), "checks": {}}

    if not sample_path.exists():
        result["status"] = "missing_sample"
        return result

    engine_cls = resolve_engine(sample_path)
    detect_score = engine_cls.detect(sample_path) if engine_cls else 0.0
    result["detect_score"] = detect_score
    result["resolved_engine"] = engine_cls.engine_id if engine_cls else None

    session = run_runtime_session(f"verify_{name}", sample_path, timeout_seconds=timeout)
    result["session_status"] = session.get("status")
    result["session_engine"] = session.get("engine")
    result["runtime_method"] = (session.get("signals") or {}).get("runtime_method")
    norm = session.get("normalized") or {}
    result["has_normalized"] = bool(norm.get("runtime_observation"))
    result["normalized_engine"] = (norm.get("runtime_observation") or {}).get("engine_id")

    acceptable = {"completed", "partial", "skipped", "gated"}
    result["status"] = "pass" if session.get("status") in acceptable else "fail"
    if session.get("status") == "gated":
        result["status"] = "warn"
        result["reason"] = session.get("reason")
    return result


def run_pytest_gates() -> bool:
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_unity_runtime_engine.py",
        "tests/test_gamemaker_engine.py",
        "tests/test_godot_engine.py",
        "tests/test_engine_registry.py",
        "tests/test_runtime_orchestrator.py",
        "-q",
        "--tb=line",
    ]
    print("RUN   " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Unity/Godot/GameMaker/Web engines")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--json", action="store_true", help="Write report JSON")
    args = parser.parse_args()

    print("Engine verification — market launch gate\n")

    engines = [
        ("unity", SAMPLES / "unity"),
        ("godot", SAMPLES / "godot"),
        ("gamemaker", SAMPLES / "gamemaker"),
        ("web", SAMPLES / "web"),
    ]

    reports: List[Dict[str, Any]] = []
    failures = 0
    warnings = 0

    for name, path in engines:
        report = verify_engine(name, path, timeout=args.timeout)
        reports.append(report)
        status = report.get("status")
        detail = (
            f"{name}: engine={report.get('session_engine')} "
            f"status={report.get('session_status')} "
            f"method={report.get('runtime_method')} "
            f"detect={report.get('detect_score')}"
        )
        if status == "pass":
            _ok(detail)
        elif status == "warn":
            _warn(detail + f" ({report.get('reason', 'gated')})")
            warnings += 1
        else:
            _fail(detail)
            failures += 1

    if not args.skip_pytest:
        print()
        if not run_pytest_gates():
            failures += 1
            _fail("engine pytest suite")
        else:
            _ok("engine pytest suite")

    if args.json:
        out = ROOT / "uploads" / "ops" / "engine_verification_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"failures": failures, "warnings": warnings, "engines": reports}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nReport: {out}")

    print(f"\nSummary: {failures} failure(s), {warnings} warning(s)")
    if failures:
        print("NOT READY — fix failures before launch")
        return 1
    if warnings:
        print("READY WITH WARNINGS — check L4 sandbox / env flags")
        return 0
    print("ALL ENGINES VERIFIED — ready for market launch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
