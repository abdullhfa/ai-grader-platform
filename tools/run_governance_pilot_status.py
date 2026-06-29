#!/usr/bin/env python3
"""Unified pilot wave + governance intelligence status."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "app/calibration/reports/closure"


def main() -> int:
    from app.calibration.governance_calibration import build_from_closure_reports

    if (REPORTS / "phase_a_disagreement.json").exists():
        cycle = build_from_closure_reports(REPORTS)
    else:
        cycle = {}

    progress_path = REPORTS / "human_labels_progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        import subprocess

        subprocess.run([sys.executable, "tools/check_human_labels_progress.py"], cwd=str(ROOT), check=False)
        progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}

    intel_path = REPORTS / "GOVERNANCE_INTELLIGENCE_REVIEW_v1.json"
    intel = json.loads(intel_path.read_text(encoding="utf-8")) if intel_path.exists() else {}

    print("=" * 60)
    print("GOVERNANCE PILOT STATUS")
    print("=" * 60)
    print(f"Human labels: {progress.get('criteria_slots_filled')} ({progress.get('criteria_pct')}%)")
    print(f"Pilot complete: {progress.get('fully_complete')}/25 fully reviewed")
    wave = cycle.get("pilot_wave_progress") or {}
    print(f"Pilot wave 11/11 ready: {wave.get('pilot_ready', False)} ({wave.get('pilot_fully_complete', 0)}/11)")
    print()
    print("Wave 1 Abdullah:", (wave.get("wave_1_abdullah") or {}).get("pct", 0), "%")
    print("Wave 2 Top 5:    ", (wave.get("wave_2_top5") or {}).get("pct", 0), "%")
    print("Wave 3 Bottom 5: ", (wave.get("wave_3_bottom5") or {}).get("pct", 0), "%")
    print()
    print(f"Governance cycle: {cycle.get('cycle_status', 'not run')}")
    matrix = cycle.get("disagreement_taxonomy_matrix") or []
    if matrix:
        print("Taxonomy findings:")
        for row in matrix:
            print(f"  {row.get('taxonomy_type')}: {row.get('count')} -> {row.get('governance_decision')}")
    else:
        print("Taxonomy: awaiting human labels")
    print()
    ref = intel.get("reference_governance_case") or {}
    pending = ref.get("pending_criteria") or []
    if pending:
        print("Abdullah pending criteria:", ", ".join(p["criterion"] for p in pending))
    print()
    print("URLs:")
    print("  Moderation:  http://127.0.0.1:5557/institutional/moderation")
    print("  Review:      http://127.0.0.1:5557/institutional/governance-review")
    print()
    print("Next:")
    for step in (cycle.get("next_steps_ar") or ["Complete Abdullah in /institutional/moderation"])[:3]:
        print(f"  - {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
