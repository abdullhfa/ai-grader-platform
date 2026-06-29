"""
Export system snapshots JSON from saved grading result files (batch exports / DB dumps).

Usage:
  python -m app.calibration.export_system_snapshots \\
    --input-dir path/to/json_exports \\
    --out app/calibration/gold_dataset/system_snapshots.json

Each input file should be one submission grading result or {grading_result: {...}} wrapper.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _load_result(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "grading_result" in data:
        return data["grading_result"]
    if isinstance(data, dict):
        return data
    raise ValueError(f"unsupported shape: {path}")


def _submission_id(result: Dict[str, Any], path: Path) -> str:
    for key in ("submission_id", "student_id", "file_path", "student_name"):
        v = result.get(key)
        if v:
            return str(v)
    return path.stem


def export_snapshots(input_dir: Path, pattern: str = "*.json") -> Dict[str, Any]:
    submissions: Dict[str, Any] = {}
    paths = sorted(input_dir.glob(pattern))
    for p in paths:
        if p.name.startswith("system_snapshots"):
            continue
        try:
            result = _load_result(p)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"skip {p}: {exc}", file=sys.stderr)
            continue
        sid = _submission_id(result, p)
        slim = {
            "criteria_results": result.get("criteria_results"),
            "evidence_layer": result.get("evidence_layer"),
            "project_profile_persisted": result.get("project_profile_persisted"),
            "assessment_trace": result.get("assessment_trace"),
        }
        submissions[sid] = slim
    return {
        "schema": "system_snapshots_export_v1",
        "source_dir": str(input_dir),
        "submission_count": len(submissions),
        "submissions": submissions,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Export system snapshots for calibration")
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pattern", type=str, default="*.json")
    args = ap.parse_args()

    if not args.input_dir.is_dir():
        print(f"input dir not found: {args.input_dir}", file=sys.stderr)
        return 1

    out_doc = export_snapshots(args.input_dir, pattern=args.pattern)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({out_doc['submission_count']} submissions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
