"""
Generate synthetic gold + system snapshot cohort for calibration pipeline testing.

NOT teacher ground truth — validates exporters and dashboards at scale (default N=100).

Usage:
  python -m app.calibration.generate_synthetic_gold_cohort --count 100 --out-dir app/calibration/gold_dataset
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Reuse mini-validation fixture builders
from app.calibration.mini_validation_human_review.run_mini_validation_human_review import (
    _FIXTURES as HR_FIXTURES,
)
from app.calibration.mini_validation_rubric_sufficiency.run_mini_validation_rubric_sufficiency import (
    _FIXTURES as RUB_FIXTURES,
)


_ARCHETYPES = [
    ("strong_no_review", "case_a_strong_no_review", True, "moderate", "easy"),
    ("runtime_no_corroboration", "case_b_runtime_no_corroboration", False, "weak", "moderate"),
    ("pattern_hints_only", "case_c_pattern_hints_only", False, "weak", "ambiguous"),
    ("cross_modal_conflict", "case_d_cross_modal_conflict", False, "moderate", "ambiguous"),
    ("sparse_noise_critical", "case_e_sparse_noise_critical", False, "weak", "ambiguous"),
]

_ITEMS_BY_HR_KEY: Dict[str, List[Dict[str, Any]]] = {
    "case_a_strong_no_review": [
        {
            "evidence_type": "code_system",
            "system": "collision_system",
            "confidence": 0.9,
            "execution_evidence": "strong",
        },
        {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
        {"evidence_type": "runtime_screenshot"},
        {"evidence_type": "video_frame"},
    ],
    "case_b_runtime_no_corroboration": [
        {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
    ],
    "case_c_pattern_hints_only": [
        {"evidence_type": "pattern_hint", "system": "collision_system"},
    ],
    "case_d_cross_modal_conflict": [
        {
            "evidence_type": "code_system",
            "system": "collision_system",
            "confidence": 0.75,
            "execution_evidence": "medium",
        },
        {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
    ],
    "case_e_sparse_noise_critical": [
        {"evidence_type": "pattern_hint", "system": "collision_system"},
    ],
}


def _build_snapshot(archetype_key: str, achieved: bool) -> Dict[str, Any]:
    from app.project_intelligence.evidence_schema import build_evidence_layer_from_profile
    from app.project_intelligence.human_review_gates import attach_human_review_gates
    from app.project_intelligence.project_profile import build_project_profile
    from app.project_intelligence.rubric_sufficiency_contracts import attach_rubric_sufficiency_shadow

    hr_builder = HR_FIXTURES.get(archetype_key)
    if not hr_builder:
        raise KeyError(archetype_key)
    layer = hr_builder()

    paths = [f"/synthetic/{archetype_key}/marker.txt"]
    profile = build_project_profile(paths)
    ev_layer = build_evidence_layer_from_profile(profile)
    ev_layer["items"] = list(_ITEMS_BY_HR_KEY.get(archetype_key) or [])
    ev_layer.update(
        {
            k: layer.get(k)
            for k in (
                "runtime_corroboration",
                "cross_modal_corroboration",
                "submission_intake",
            )
            if layer.get(k)
        }
    )
    if layer.get("rubric_sufficiency_shadow"):
        ev_layer["rubric_sufficiency_shadow"] = layer["rubric_sufficiency_shadow"]

    grading_stub = {
        "criteria_results": [
            {
                "criteria_level": "A.P3",
                "achieved": achieved,
                "reasoning": "synthetic cohort — LLM slice not exercised",
            }
        ]
    }
    attach_rubric_sufficiency_shadow(grading_stub, ev_layer, profile=profile)
    attach_human_review_gates(grading_stub, ev_layer)

    cr = grading_stub["criteria_results"][0]
    return {
        "criteria_results": [cr],
        "evidence_layer": ev_layer,
        "assessment_trace": {"rubric_version": "synthetic", "calibration_run_id": "synthetic_cohort"},
    }


def generate_cohort(count: int) -> tuple[Dict[str, Any], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    submissions: Dict[str, Any] = {}

    for i in range(count):
        arch = _ARCHETYPES[i % len(_ARCHETYPES)]
        arch_name, hr_key, teacher_ach, strength, complexity = arch
        sid = f"SYNTH_{i:04d}_{arch_name}"
        crit = "P3"

        system_achieved = teacher_ach if arch_name == "strong_no_review" else (not teacher_ach)
        if arch_name == "cross_modal_conflict":
            system_achieved = True
        if arch_name == "sparse_noise_critical":
            system_achieved = False

        snap = _build_snapshot(hr_key, system_achieved)
        submissions[sid] = snap

        reviewer_tax: List[str] = []
        if not teacher_ach and system_achieved:
            reviewer_tax.append("confirmed_fp_synthetic")
        if teacher_ach and not system_achieved:
            reviewer_tax.append("confirmed_fn_synthetic")

        records.append(
            {
                "submission_id": sid,
                "unit": "SYNTHETIC_Unit_GameDev",
                "criterion": crit,
                "submission_archetype": arch_name,
                "cohort_tags": ["synthetic", arch_name],
                "teacher_result": {"achieved": teacher_ach, "confidence": 0.85},
                "teacher_evidence_strength": strength,
                "review_complexity": complexity,
                "reviewer_taxonomy": reviewer_tax,
                "teacher_notes": [f"synthetic archetype {arch_name}"],
                "accepted_evidence": ["synthetic_accepted"] if teacher_ach else [],
                "rejected_evidence": ["synthetic_rejected"] if not teacher_ach else [],
            }
        )

    gold_doc = {
        "schema": "unity_calibration_gold_v2",
        "synthetic": True,
        "description": "Synthetic cohort for calibration pipeline validation — NOT teacher ground truth.",
        "target_count": count,
        "records": records,
    }
    sys_doc = {
        "schema": "system_snapshots_export_v1",
        "synthetic": True,
        "submission_count": len(submissions),
        "submissions": submissions,
    }
    return gold_doc, sys_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--out-dir", type=Path, default=Path("app/calibration/gold_dataset"))
    args = ap.parse_args()

    if args.count < 1 or args.count > 500:
        print("count must be 1..500", file=sys.stderr)
        return 1

    gold, systems = generate_cohort(args.count)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    gold_path = args.out_dir / "unity_gold_synthetic_cohort_v1.json"
    sys_path = args.out_dir / "system_snapshots_synthetic_cohort_v1.json"
    gold_path.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    sys_path.write_text(json.dumps(systems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {gold_path} ({len(gold['records'])} records)")
    print(f"Wrote {sys_path} ({systems['submission_count']} submissions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
