#!/usr/bin/env python3
"""Start canary rollout — ship stack, verify engines, record cohort phase."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(label: str, cmd: list[str]) -> int:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    print("RUN  ", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def write_canary_record(base_url: str, *, instructor_count: int, notes: str) -> Path:
    out = ROOT / "uploads" / "ops" / "canary_rollout.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "phase": "canary_rollout",
        "status": "active",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "cohort": {
            "instructor_target": instructor_count,
            "duration_weeks_min": 2,
            "duration_weeks_max": 4,
            "replay_retention": "max",
            "tracing": "verbose",
        },
        "kpis": {
            "replay_mismatch": 0,
            "runtime_success_rate_pct_min": 95,
            "dead_letters_max": 0,
        },
        "monitor": {
            "dashboard": f"{base_url.rstrip('/')}/api/ops/dashboard",
            "sla": f"{base_url.rstrip('/')}/api/ops/sla",
            "metrics": f"{base_url.rstrip('/')}/api/metrics",
            "grafana": "http://localhost:3000",
            "prometheus": "http://localhost:9091",
        },
        "runbook": "infra/runbooks/CANARY_ROLLOUT.md",
        "pentest_pack": "infra/pentest/",
        "notes": notes,
        "next_steps": [
            "Assign 5-10 pilot instructors (isolated course/org)",
            "Enable RBAC roles: examiner / instructor / student",
            "Hand off infra/pentest/ to external team",
            "Daily: python tools/verify_operational_signals.py",
            "Weekly: review replay_mismatch + dead_letter.jsonl",
        ],
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Start canary rollout")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--instructors", type=int, default=5)
    parser.add_argument("--skip-ship", action="store_true", help="Skip docker deploy (stack already up)")
    parser.add_argument("--skip-build", action="store_true", help="Pass --skip-build to ship.py")
    parser.add_argument("--notes", default="Canary rollout started — Ship → Observe → Sell")
    args = parser.parse_args()

    print("CANARY ROLLOUT — Ship → Observe → Sell\n")

    if not args.skip_ship:
        ship_cmd = [sys.executable, str(ROOT / "tools" / "ship.py")]
        if args.skip_build:
            ship_cmd.append("--skip-build")
        code = run_step("Step 1 — Ship stack", ship_cmd)
        if code != 0:
            print("\nFAIL  ship.py — fix deploy before canary")
            return code
    else:
        print("SKIP  ship.py (--skip-ship)")

    code = run_step(
        "Step 2 — Verify engines",
        [sys.executable, str(ROOT / "tools" / "verify_engines.py"), "--json"],
    )
    if code != 0:
        print("\nFAIL  engine verification — fix before canary")
        return code

    code = run_step(
        "Step 3 — Operational signals",
        [
            sys.executable,
            str(ROOT / "tools" / "verify_operational_signals.py"),
            "--base-url",
            args.base_url,
        ],
    )
    if code != 0:
        print("\nFAIL  operational signals — investigate before expanding cohort")
        return code

    record_path = write_canary_record(args.base_url, instructor_count=args.instructors, notes=args.notes)
    print(f"\nOK    Canary record: {record_path.relative_to(ROOT)}")
    print("\nCANARY ACTIVE")
    print(f"  Base URL:     {args.base_url}")
    print(f"  Instructors:  {args.instructors} (target 5-10)")
    print(f"  Runbook:      infra/runbooks/CANARY_ROLLOUT.md")
    print(f"  Pentest pack: infra/pentest/")
    print("\nDaily monitor:")
    print(f"  python tools/verify_operational_signals.py --base-url {args.base_url}")
    print("\nObserve → Sell. No new features until KPIs hold 2-4 weeks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
