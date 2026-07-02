"""
Unit 9 games — offline calibration on uploads/تجربة folders (no Gemini).

Builds artifact inventory, evidence coverage, Runtime Gate, Evidence Map summary.

Usage:
  python scripts/run_unit9_calibration.py
  python scripts/run_unit9_calibration.py --sample "Ahmad Bakr"
  python scripts/run_unit9_calibration.py --include-baseline-48
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO.parent / "uploads" / "تجربة"
REPORT_DIR = REPO / "app" / "calibration" / "grades" / "grade_10" / "games" / "reports"

UNIT9_CRITERIA = [
    "8/B.P3", "8/B.P4", "8/C.P5", "8/C.P6", "8/C.P7",
    "8/B.M2", "8/C.M3", "8/BC.D2", "8/BC.D3",
]

PRIORITY_SUFFIXES = (
    ".exe", ".sb3", ".sb2", ".pck", ".uproject", ".yyp", ".yy",
    ".docx", ".pdf", ".pptx", ".mp4", ".mov", ".gd", ".tscn", ".unity",
)
MAX_PATHS = 2500


def _collect_paths(folder: Path) -> List[str]:
    files = [p for p in folder.rglob("*") if p.is_file()]
    # Skip Unity Library noise
    files = [p for p in files if "library" not in str(p).lower().replace("\\", "/") or "/assets/" in str(p).replace("\\", "/").lower()]

    def rank(p: Path) -> tuple:
        rel = str(p).lower()
        pri = 0
        for i, suf in enumerate(PRIORITY_SUFFIXES):
            if rel.endswith(suf) or suf.strip(".") in rel:
                pri = len(PRIORITY_SUFFIXES) - i
                break
        if p.name.lower() == "project.godot":
            pri = len(PRIORITY_SUFFIXES) + 5
        return (-pri, len(rel))

    files.sort(key=rank)
    selected = files[:MAX_PATHS]
    return [str(p) for p in selected]


def _stub_criteria(*, achieved: bool = True) -> List[Dict[str, Any]]:
    return [
        {
            "criteria_level": level,
            "achieved": achieved,
            "awardable": achieved,
            "score": 80 if achieved else 0,
        }
        for level in UNIT9_CRITERIA
    ]


def calibrate_folder(
    folder: Path,
    *,
    label: str,
    skip_heavy: bool = True,
) -> Dict[str, Any]:
    from app.artifact_inventory import build_artifact_inventory
    from app.btec_criteria_governance import apply_btec_awardability
    from app.criteria_result_finalizer import finalize_grading_criteria_results
    from app.evidence_coverage_score import attach_evidence_coverage_package
    from app.evidence_map import build_evidence_map, build_evidence_map_summary
    from app.official_grade import resolve_official_grade
    from app.runtime_evidence_gate import is_game_submission
    from app.unit_calibration import assess_moe_engine_compliance

    paths = _collect_paths(folder)
    inv = build_artifact_inventory(
        submission_paths=paths,
        student_name=label,
        skip_runtime_observation=True,
        skip_heavy_enrichment=skip_heavy,
        skip_l2_l3_corroborative=True,
        skip_governance_graphs=True,
        grading_mode="deep",
    )

    snap: Dict[str, Any] = {
        "grading_mode": "deep",
        "submission_paths": paths,
        "artifact_inventory": inv,
        "criteria_results": _stub_criteria(achieved=True),
        "student_text": "",
        "grade_level": "D",
        "percentage": 80,
    }

    attach_evidence_coverage_package(snap, student_text="")
    finalize_grading_criteria_results(snap)
    official = resolve_official_grade(snap, reapply_pipeline=True)

    ev_rows = build_evidence_map(snap)
    ev_sum = build_evidence_map_summary(ev_rows)
    moe = assess_moe_engine_compliance(submission_paths=paths)

    gate = snap.get("runtime_evidence_gate") or {}
    gated = [
        r["criterion_level"]
        for r in ev_rows
        if r.get("gate_applied") and r.get("gate_satisfied") is False
    ]

    runtime_rows = {
        r["criterion_code"]: {
            "found": r.get("available_evidence"),
            "missing": r.get("missing_evidence"),
            "coverage": r.get("coverage_score"),
        }
        for r in ev_rows
        if r.get("criterion_code") in ("P5", "P6", "M3", "D3")
    }

    return {
        "label": label,
        "folder": str(folder),
        "path_count": len(paths),
        "file_count_scanned": len(paths),
        "engine_inventory": (inv.get("runtime_artifacts") or {}),
        "moe_compliance": moe,
        "is_game": is_game_submission(inv, submission_paths=paths),
        "runtime_gate": {
            "applied": gate.get("applied"),
            "satisfied": gate.get("satisfied"),
            "status": gate.get("status"),
            "accepted_evidence": gate.get("accepted_evidence"),
        },
        "official_grade": official.grade,
        "official_source": official.source,
        "evidence_summary": ev_sum,
        "runtime_criteria_evidence": runtime_rows,
        "gate_blocked_levels": gated,
        "path_sample": [Path(p).name for p in paths[:8]],
    }


def calibrate_submission_48() -> Dict[str, Any]:
    import sqlite3

    from app.evidence_map import (
        build_evidence_map,
        build_evidence_map_summary,
        build_evidence_summary_from_snapshot,
    )
    from app.official_grade import resolve_official_grade
    from app.unit_calibration import assess_moe_engine_compliance

    db = REPO / "ai_grader.db"
    if not db.is_file():
        return {"label": "العاب (submission 48)", "error": "ai_grader.db not found"}

    row = sqlite3.connect(db).execute(
        "SELECT grading_snapshot_json FROM submissions WHERE id=48"
    ).fetchone()
    if not row or not row[0]:
        return {"label": "العاب (submission 48)", "error": "no snapshot"}

    snap = json.loads(row[0])
    resolve_official_grade(snap, reapply_pipeline=True)
    official = resolve_official_grade(snap)
    paths = snap.get("submission_paths") or []
    ev_rows = build_evidence_map(snap)
    return {
        "label": "العاب (submission 48)",
        "submission_id": 48,
        "batch_id": 53,
        "moe_compliance": assess_moe_engine_compliance(submission_paths=list(paths)),
        "official_grade": official.grade,
        "evidence_summary": build_evidence_summary_from_snapshot(snap),
        "runtime_criteria_evidence": {
            r["criterion_code"]: {
                "found": r.get("available_evidence"),
                "missing": r.get("missing_evidence"),
            }
            for r in ev_rows
            if r.get("criterion_code") in ("P5", "P6", "M3", "D3")
        },
        "gate_blocked_levels": [
            r["criterion_level"]
            for r in ev_rows
            if r.get("gate_applied") and r.get("gate_satisfied") is False
        ],
    }


def _find_folder(root: Path, needle: str) -> Optional[Path]:
    needle_l = needle.lower()
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and needle_l in entry.name.lower():
            return entry
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Unit 9 calibration run on تجربة samples")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--sample", action="append", default=[], help="Subfolder name filter (repeatable)")
    parser.add_argument("--include-baseline-48", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"Not found: {args.root}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(REPO))

    targets = args.sample or ["Ahmad Bakr", "GAME B"]
    results: List[Dict[str, Any]] = []

    if args.include_baseline_48:
        results.append(calibrate_submission_48())

    for needle in targets:
        folder = _find_folder(args.root, needle)
        if not folder:
            results.append({"label": needle, "error": f"folder not found under {args.root}"})
            continue
        print(f"Calibrating: {folder.name} ...", file=sys.stderr)
        try:
            results.append(calibrate_folder(folder, label=folder.name))
        except Exception as exc:
            results.append({"label": folder.name, "error": str(exc)})

    report = {
        "unit": "grade_10/games",
        "run_date": str(date.today()),
        "samples": results,
    }

    out = args.json_out or (REPORT_DIR / f"calibration_{date.today().isoformat()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json_out:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Report: {out}\n")
        for r in results:
            if r.get("error"):
                print(f"✗ {r.get('label')}: {r['error']}")
                continue
            print(f"• {r.get('label')}")
            print(f"    grade={r.get('official_grade')} game={r.get('is_game')} gate={r.get('runtime_gate')}")
            moe = r.get("moe_compliance") or {}
            print(f"    MOE engine={moe.get('engine')} compliant={moe.get('compliant')}")
            es = r.get("evidence_summary") or {}
            print(f"    gate_issues={es.get('has_gate_issue')} blocked={r.get('gate_blocked_levels')}")
            rt = r.get("runtime_criteria_evidence") or {}
            if rt.get("P5"):
                print(f"    P5 found={rt['P5'].get('found')} missing={rt['P5'].get('missing')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
