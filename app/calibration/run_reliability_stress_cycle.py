"""
Run full reliability stress cycle: generate cohort → calibration report → archetype summary.

Does NOT change thresholds or wire shadow to achieved.

Usage:
  python -m app.calibration.run_reliability_stress_cycle
  python -m app.calibration.run_reliability_stress_cycle --count 50 --freeze-window freeze_stress_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from app.calibration.calibration_report import build_calibration_report, pick_meta
from app.calibration.generate_reliability_stress_cohort import generate_stress_cohort


def _archetype_summary(report: Dict[str, Any], gold_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    arch_by_sid = {r["submission_id"]: r.get("submission_archetype") for r in gold_records}
    focus_by_sid = {r["submission_id"]: r.get("stress_focus") or [] for r in gold_records}

    by_arch: Dict[str, Dict[str, int]] = defaultdict(lambda: Counter())
    review_by_arch: Dict[str, List[bool]] = defaultdict(list)

    for row in report.get("per_row") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("submission_id") or "")
        arch = arch_by_sid.get(sid) or "unknown"
        t_ach = bool(row.get("teacher_achieved"))
        s_ach = bool(row.get("system_achieved"))
        if t_ach and s_ach:
            outcome = "true_positive"
        elif not t_ach and s_ach:
            outcome = "false_positive"
        elif t_ach and not s_ach:
            outcome = "false_negative"
        else:
            outcome = "true_negative"
        by_arch[arch][outcome] += 1
        snap = row.get("shadow_signals") or {}
        rg = snap.get("human_review_required")
        if rg is not None:
            review_by_arch[arch].append(bool(rg))

    arch_rows = []
    for arch, counts in sorted(by_arch.items()):
        total = sum(counts.values())
        fp = counts.get("false_positive", 0)
        revs = review_by_arch.get(arch) or []
        arch_rows.append(
            {
                "archetype": arch,
                "pairs": total,
                "false_positives": fp,
                "false_negatives": counts.get("false_negative", 0),
                "true_positives": counts.get("true_positive", 0),
                "true_negatives": counts.get("true_negative", 0),
                "fp_rate_within_archetype": round(fp / total, 4) if total else 0.0,
                "human_review_required_rate": round(sum(revs) / len(revs), 4) if revs else None,
            }
        )

    return {
        "archetype_breakdown": arch_rows,
        "top_fp_archetypes": sorted(arch_rows, key=lambda x: -x["false_positives"])[:10],
        "stress_focus_sample": {
            sid: focus_by_sid.get(sid) for sid in list(focus_by_sid.keys())[:5]
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Reliability stress calibration cycle")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--out-dir", type=Path, default=Path("app/calibration/gold_dataset"))
    ap.add_argument("--reports-dir", type=Path, default=Path("app/calibration/reports"))
    ap.add_argument("--run-id", type=str, default="cal_reliability_stress_v1")
    ap.add_argument("--freeze-window", type=str, default="freeze_reliability_stress_v1")
    ap.add_argument("--skip-generate", action="store_true")
    args = ap.parse_args()

    gold_path = args.out_dir / "unity_gold_reliability_stress_v1.json"
    sys_path = args.out_dir / "system_snapshots_reliability_stress_v1.json"

    if not args.skip_generate:
        gold, systems = generate_stress_cohort(args.count)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        gold_path.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
        sys_path.write_text(json.dumps(systems, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Generated stress cohort: {args.count} cases")

    if not gold_path.is_file() or not sys_path.is_file():
        print("gold/systems missing; run without --skip-generate", file=sys.stderr)
        return 1

    report = build_calibration_report(
        gold_path,
        sys_path,
        run_id=pick_meta(args.run_id, "CALIBRATION_RUN_ID"),
        rubric_version=pick_meta(None, "RUBRIC_VERSION") or "1.0",
        freeze_window_id=args.freeze_window,
    )

    gold_data = json.loads(gold_path.read_text(encoding="utf-8"))
    records = list(gold_data.get("records") or [])
    summary = _archetype_summary(report, records)
    report["stress_operational_summary"] = {
        "cohort_type": "reliability_stress",
        "not_production_validation": True,
        **summary,
    }

    args.reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.reports_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    m = report.get("metrics") or {}
    sd = report.get("shadow_dashboard") or {}
    rg = (sd.get("review_gate_dashboard") or {}) if isinstance(sd, dict) else {}
    print(f"Wrote {out_path}")
    print(
        f"pairs={report.get('cohort_summary', {}).get('pairs_compared')} "
        f"FP={m.get('false_positives')} FN={m.get('false_negatives')} "
        f"FP_rate={m.get('false_positive_rate')} "
        f"review_required_rate={rg.get('human_review_required_rate')}"
    )
    print("Top FP archetypes:")
    for row in summary.get("top_fp_archetypes") or []:
        print(f"  {row['archetype']}: FP={row['false_positives']} review_rate={row['human_review_required_rate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
