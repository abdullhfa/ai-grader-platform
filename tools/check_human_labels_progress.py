#!/usr/bin/env python3
"""Report human_labels_v1 completion — no fabricated decisions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LABELS = ROOT / "app/calibration/human_labels_v1.json"
CRITERIA = ("P3", "P4", "P5", "P6", "P7", "M2", "M3", "D2", "D3")

# Pilot priority cohort (batch #5 + Abdullah)
PRIORITY_WAVE_1 = [1]  # Abdullah
PRIORITY_WAVE_2 = [22, 15, 19, 14, 16]  # top 5 by AI pct (batch 5)
PRIORITY_WAVE_3 = [20, 21, 17, 18, 25]  # bottom 5


def _filled(rec: dict) -> dict:
    crit = rec.get("criteria") or {}
    filled = sum(1 for k in CRITERIA if (crit.get(k) or {}).get("decision") is not None)
    overall = rec.get("overall_grade") is not None
    return {
        "submission_id": rec.get("submission_id"),
        "student": rec.get("student_name_ar") or rec.get("student"),
        "criteria_filled": filled,
        "criteria_total": len(CRITERIA),
        "overall_filled": overall,
        "complete": filled == len(CRITERIA) and overall,
        "pct": round((filled + (1 if overall else 0)) / (len(CRITERIA) + 1) * 100, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Human labels completion tracker")
    parser.add_argument("--labels", default=str(LABELS))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    doc = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    rows = [_filled(r) for r in doc.get("records") or []]
    complete = sum(1 for r in rows if r["complete"])
    total_crit_slots = sum(r["criteria_filled"] for r in rows)
    max_crit = len(rows) * len(CRITERIA)

    def wave(ids: list[int]) -> list[dict]:
        idset = set(ids)
        return [r for r in rows if r["submission_id"] in idset]

    report = {
        "total_records": len(rows),
        "fully_complete": complete,
        "criteria_slots_filled": f"{total_crit_slots}/{max_crit}",
        "criteria_pct": round(total_crit_slots / max(max_crit, 1) * 100, 1),
        "wave_1_abdullah": wave(PRIORITY_WAVE_1),
        "wave_2_top5": wave(PRIORITY_WAVE_2),
        "wave_3_bottom5": wave(PRIORITY_WAVE_3),
        "all_records": rows,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== Human Labels Progress ===")
        print(f"Records: {len(rows)} | Fully complete: {complete}/{len(rows)}")
        print(f"Criteria slots: {total_crit_slots}/{max_crit} ({report['criteria_pct']}%)")
        print("\nWave 1 — Abdullah:")
        for r in wave(PRIORITY_WAVE_1):
            print(f"  #{r['submission_id']} {r['student']}: {r['pct']}% ({r['criteria_filled']}/9 + overall)")
        print("\nWave 2 — Top 5 (fill next):")
        for r in wave(PRIORITY_WAVE_2):
            print(f"  #{r['submission_id']} {r['student']}: {r['pct']}%")
        print("\nWave 3 — Bottom 5:")
        for r in wave(PRIORITY_WAVE_3):
            print(f"  #{r['submission_id']} {r['student']}: {r['pct']}%")
        if complete < len(rows):
            print("\nNEXT: Fill app/calibration/human_labels_v1.json then run:")
            print("  .venv\\Scripts\\python.exe tools\\run_institutional_closure.py")

    out = ROOT / "app/calibration/reports/closure/human_labels_progress.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
