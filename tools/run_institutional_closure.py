#!/usr/bin/env python3
"""Institutional Closure — Phases A–G autonomous execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.calibration.closure.phase_runner import run_full_closure


def main() -> int:
    parser = argparse.ArgumentParser(description="Institutional Closure Phases A–G")
    parser.add_argument("--no-runtime", action="store_true", help="Skip live sandbox probes")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    result = run_full_closure(run_runtime=not args.no_runtime, skip_tests=args.skip_tests)
    phases = result.get("phases") or {}

    print("=" * 60)
    print("INSTITUTIONAL CLOSURE COMPLETE")
    print("=" * 60)
    for key in ("A", "B", "C", "D", "E", "F", "G"):
        p = phases.get(key, {})
        print(f"PHASE {key}: {p.get('status', 'n/a')}")
    if "tests" in phases:
        for k, v in phases["tests"].items():
            print(f"  TEST {k}: {'OK' if v.get('ok') else 'FAIL'}")

    print(f"\nManifest: app/calibration/reports/closure/CLOSURE_MANIFEST.json")
    print(f"Exit OK: {result.get('exit_ok')}")

    gc = phases.get("governance_calibration") or {}
    print(f"\nGovernance Calibration Cycle: {gc.get('status', 'n/a')}")
    if gc.get("taxonomy_matrix"):
        print("Disagreement taxonomy:")
        for row in gc["taxonomy_matrix"]:
            print(f"  - {row.get('taxonomy_type')}: {row.get('count')} → {row.get('governance_decision')}")
    else:
        print("  (awaiting human labels wave — fill /institutional/moderation)")

    b = phases.get("B", {}).get("taxonomy_counts") or {}
    print(f"Runtime taxonomy: {json.dumps(b, ensure_ascii=False)}")
    print(f"Replay: {phases.get('C', {}).get('stable')}")
    print(f"Moderation queue: {phases.get('F', {}).get('moderation_queue_length')} items PENDING_HUMAN")
    print(f"\nPilot status: .venv\\Scripts\\python.exe tools\\run_governance_pilot_status.py")
    print(f"Intelligence review: app/calibration/reports/closure/GOVERNANCE_INTELLIGENCE_REVIEW.md")

    return 0 if result.get("exit_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
