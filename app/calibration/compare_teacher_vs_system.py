"""
Compare teacher gold labels to system grading output (per criterion).

Usage (from project root):
  .venv\\Scripts\\python -m app.calibration.compare_teacher_vs_system \\
    --gold app/calibration/gold_dataset/unity_gold_submission_v1.json \\
    --systems path/to/system_snapshots.json

system_snapshots.json shape:
  { "submissions": { "<submission_id>": { ... grading_snapshot / batch result ... } } }
or
  [ { "submission_id": "...", "criteria_results": [ {"criteria_level":"A.P3","achieved": true}, ... ] }, ... ]

Does NOT modify thresholds — read-only metrics for calibration Phase 1.

Gold rows may optionally include:
  teacher_evidence_strength: "weak" | "moderate" | "strong"
  review_complexity: "easy" | "moderate" | "ambiguous"
  reviewer_taxonomy: list[str] — human-confirmed error tags after review (overrides heuristics for reporting later)

Each compared row includes taxonomy_suggestion.evidence_density (counts per system / type)
and taxonomy_tag_confidence (heuristic scores per suggested tag — for review only).
Per-system calibration: interpret confidence and density per `by_system` key, not one global rule.

Report includes `false_positive_density_report` (schema fp_density_v2): means, percentiles,
histograms per subsystem on FP rows, plus `fp_empty_evidence_layer_ratio` for LLM-overclaim drift tracking.

`reliability_run` holds UTC timestamp and optional version ids for temporal regression (diff reports across runs).
CLI overrides env: CALIBRATION_RUN_ID, RUBRIC_VERSION, EXTRACTOR_VERSION.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.calibration.error_taxonomy import (
    DENSITY_REPORT_SCHEMA,
    TAXONOMY_VERSION,
    aggregate_fp_density_by_system,
    merge_taxonomy_counts,
    suggest_mismatch_tags,
)
from app.calibration.taxonomy_helpers import criteria_match


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _index_system_by_submission(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict) and "submissions" in raw:
        return {str(k): v for k, v in raw["submissions"].items()}
    if isinstance(raw, list):
        out: Dict[str, Any] = {}
        for row in raw:
            sid = str(row.get("submission_id") or row.get("id") or "")
            if sid:
                out[sid] = row
        return out
    raise ValueError("system JSON must be {submissions:{...}} or list of rows with submission_id")


def _system_achieved_for_criterion(snapshot: Dict[str, Any], gold_crit: str) -> Optional[bool]:
    for cr in snapshot.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        lvl = str(cr.get("criteria_level") or "")
        if criteria_match(lvl, gold_crit):
            return bool(cr.get("achieved"))
    return None


def _load_gold_records(gold_path: Path) -> List[Dict[str, Any]]:
    data = _load_json(gold_path)
    if isinstance(data, dict) and "records" in data:
        return list(data["records"])
    if isinstance(data, list):
        return data
    raise ValueError("gold file must contain {records: [...]} or be a bare list")


def compute_confusion(
    pairs: List[Tuple[bool, bool]],
) -> Tuple[int, int, int, int]:
    tp = fp = fn = tn = 0
    for t, s in pairs:
        if t and s:
            tp += 1
        elif not t and s:
            fp += 1
        elif t and not s:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def _pick_meta(cli_val: Optional[str], env_key: str) -> Optional[str]:
    v = (cli_val or "").strip()
    if v:
        return v
    ev = os.environ.get(env_key)
    return ev.strip() if ev else None


def build_reliability_run_metadata(
    *,
    gold_path: Path,
    systems_path: Path,
    gold_file_top: Any,
    run_id: Optional[str],
    rubric_version: Optional[str],
    extractor_version: Optional[str],
) -> Dict[str, Any]:
    gold_schema = None
    if isinstance(gold_file_top, dict):
        gold_schema = gold_file_top.get("schema")

    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "run_id": run_id,
        "rubric_version": rubric_version,
        "extractor_version": extractor_version,
        "inputs": {
            "gold_path": str(gold_path),
            "systems_path": str(systems_path),
        },
        "gold_dataset_schema": gold_schema,
        "report_schemas": {
            "false_positive_density": DENSITY_REPORT_SCHEMA,
            "taxonomy_suggestions": TAXONOMY_VERSION,
        },
        "temporal_diff_hint": "Store this JSON per run; compare reliability_run + metrics + false_positive_density_report for drift.",
    }


def main() -> int:
    from app.calibration.calibration_report import build_calibration_report, pick_meta

    ap = argparse.ArgumentParser(description="Teacher gold vs system — calibration metrics")
    ap.add_argument("--gold", type=Path, required=True, help="Path to unity_gold_*.json")
    ap.add_argument("--systems", type=Path, required=True, help="Path to exported system snapshots JSON")
    ap.add_argument("--run-id", type=str, default=None, help="Logical run id (or set CALIBRATION_RUN_ID)")
    ap.add_argument("--rubric-version", type=str, default=None, help="Rubric / shadow version label (or RUBRIC_VERSION)")
    ap.add_argument(
        "--extractor-version",
        type=str,
        default=None,
        help="Extractor / pipeline version when snapshots were built (or EXTRACTOR_VERSION)",
    )
    ap.add_argument("--freeze-window", type=str, default=None)
    args = ap.parse_args()

    report = build_calibration_report(
        args.gold,
        args.systems,
        run_id=pick_meta(args.run_id, "CALIBRATION_RUN_ID"),
        rubric_version=pick_meta(args.rubric_version, "RUBRIC_VERSION"),
        extractor_version=pick_meta(args.extractor_version, "EXTRACTOR_VERSION"),
        freeze_window_id=(args.freeze_window or "").strip() or None,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
