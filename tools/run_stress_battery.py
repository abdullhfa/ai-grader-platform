#!/usr/bin/env python3
"""Run PHASE C runtime stress battery."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime.stress_harness import run_full_stress_battery, run_stress_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE C runtime stress battery")
    parser.add_argument("--scenario", default="", help="Single scenario id")
    parser.add_argument("--out", default="", help="Output JSON path")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    if args.scenario:
        report = run_stress_scenario(args.scenario)
    else:
        report = run_full_stress_battery()

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.json_only or args.out:
        print(text)
    else:
        count = report.get("scenario_count") or 1
        passed = report.get("scenarios_passed") or (1 if report.get("detect_crash") is not None else 0)
        print(f"Stress battery: {passed}/{count} scenarios handled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
