"""
Reliability Stress Cohort — failure-oriented synthetic operational submissions.

NOT production validation. Exercises corroboration, sufficiency shadow, review gates,
and calibration dashboards under designed failure modes (~50 cases by default).

Usage:
  python -m app.calibration.generate_reliability_stress_cohort
  python -m app.calibration.generate_reliability_stress_cohort --count 50 --out-dir app/calibration/gold_dataset
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.calibration.mini_validation_human_review.run_mini_validation_human_review import (
    _FIXTURES as HR_FIXTURES,
)


LayerBuilder = Callable[[], Dict[str, Any]]


def _shadow(sufficient: bool, flags: List[str]) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "shadow_mode": "observation_only",
        "by_criterion": {
            "A.P3": {
                "contract_id": "game_collision_p3",
                "sufficient": sufficient,
                "insufficiency_flags": [{"flag": f} for f in flags],
            }
        },
    }


def _layer_strong() -> Dict[str, Any]:
    return HR_FIXTURES["case_a_strong_no_review"]()


def _layer_runtime_fake() -> Dict[str, Any]:
    return HR_FIXTURES["case_b_runtime_no_corroboration"]()


def _layer_pattern_only() -> Dict[str, Any]:
    return HR_FIXTURES["case_c_pattern_hints_only"]()


def _layer_cross_conflict() -> Dict[str, Any]:
    return HR_FIXTURES["case_d_cross_modal_conflict"]()


def _layer_noisy() -> Dict[str, Any]:
    return HR_FIXTURES["case_e_sparse_noise_critical"]()


def _layer_screenshots_only() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "runtime_screenshot", "detail": "menu_screen"},
            {"evidence_type": "runtime_screenshot", "detail": "generic_ui"},
        ],
        "runtime_corroboration": {"corroboration_conflicts": [], "missing_runtime_corroboration_flags": []},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.2},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["pattern_hints_only_insufficient"]),
    }


def _layer_ocr_misleading() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "ocr_text", "text": "Score: 100", "confidence": 0.95},
            {"evidence_type": "ocr_text", "text": "Achievement Unlocked", "confidence": 0.88},
        ],
        "runtime_corroboration": {"corroboration_conflicts": []},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.15},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["ocr_video_without_corroboration"]),
    }


def _layer_systems_no_runtime() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.82,
                "execution_evidence": "medium",
            }
        ],
        "runtime_corroboration": {
            "corroboration_conflicts": [],
            "missing_runtime_corroboration_flags": [
                {"flag": "collision_system_detected_without_runtime_signal", "system": "collision_system"}
            ],
        },
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.1},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["missing_runtime_corroboration"]),
    }


def _layer_video_only_code() -> Dict[str, Any]:
    """collision_system in code, video only — no log/screenshot."""
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.88,
                "execution_evidence": "strong",
            },
            {"evidence_type": "video_frame", "frame_index": 12},
        ],
        "runtime_corroboration": {
            "by_system": {
                "collision_system": {
                    "corroboration_modalities": ["code_system", "video_frame"],
                    "corroboration_strength": "weak",
                }
            },
            "corroboration_conflicts": [],
            "missing_runtime_corroboration_flags": [
                {"flag": "collision_system_detected_without_runtime_signal", "system": "collision_system"}
            ],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.35,
            "cross_modal_noise_flags": [
                {"flag": "video_frames_present_without_temporal_overlap", "detail": "no_video_windows"}
            ],
        },
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["ocr_video_without_corroboration"]),
    }


def _layer_video_only_windows() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "video_frame"},
            {"evidence_type": "video_frame", "frame_index": 40},
        ],
        "runtime_corroboration": {"corroboration_conflicts": []},
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.2,
            "cross_modal_noise_flags": [
                {"flag": "video_frames_present_without_temporal_overlap", "detail": "stress_sim"}
            ],
        },
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["ocr_video_without_corroboration"]),
    }


def _layer_corrupt_sparse() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [],
        "runtime_corroboration": {},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.0},
        "submission_intake": {
            "submission_noise_flags": [
                {"flag": "archive_corrupted_or_unreadable"},
                {"flag": "high_multipart_file_count"},
            ],
            "upload_diagnostics": {
                "ignore_ratio": 0.91,
                "ignored_files": 400,
                "total_files_uploaded": 440,
                "extract_errors": ["zip_bad_crc", "truncated_archive"],
            },
        },
        "rubric_sufficiency_shadow": _shadow(False, ["empty_evidence_layer"]),
    }


def _layer_weak_corroboration() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.55,
                "execution_evidence": "weak",
            },
            {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": False}},
        ],
        "runtime_corroboration": {
            "by_system": {
                "collision_system": {
                    "corroboration_modalities": ["code_system"],
                    "corroboration_strength": "weak",
                }
            },
            "corroboration_conflicts": [],
        },
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.3},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["corroboration_conflict_detected"]),
    }


def _layer_borderline_near_pass() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.72,
                "execution_evidence": "medium",
            },
            {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
            {"evidence_type": "runtime_screenshot"},
        ],
        "runtime_corroboration": {
            "by_system": {
                "collision_system": {
                    "corroboration_modalities": ["code_system", "runtime_log", "runtime_screenshot"],
                    "corroboration_strength": "medium",
                }
            },
            "corroboration_conflicts": [],
        },
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.55},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(True, []),
    }


def _layer_false_overlap() -> Dict[str, Any]:
    """Runtime + pattern hint suggest corroboration without code confirmation."""
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "pattern_hint", "system": "collision_system"},
            {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
            {"evidence_type": "runtime_screenshot"},
        ],
        "runtime_corroboration": {
            "corroboration_conflicts": [
                {"flag": "runtime_log_present_without_matching_system", "mention_key": "mentions_collision"}
            ],
        },
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.45},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["pattern_hints_only_insufficient"]),
    }


def _layer_runtime_stale() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}, "stale": True},
            {"evidence_type": "video_frame"},
        ],
        "runtime_corroboration": {
            "missing_runtime_corroboration_flags": [
                {"flag": "runtime_evidence_stale_or_misaligned", "system": "collision_system"}
            ],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.28,
            "cross_modal_noise_flags": [
                {"flag": "video_frames_present_without_temporal_overlap"},
            ],
        },
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(
            False, ["runtime_present_without_system_confirmation"]
        ),
    }


def _layer_ocr_video_no_corr() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "ocr_text", "text": "Player HP: 100"},
            {"evidence_type": "video_frame"},
        ],
        "runtime_corroboration": {},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.25},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["ocr_video_without_corroboration"]),
    }


def _layer_inflation_weak_code() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.4,
                "execution_evidence": "weak",
            },
            {"evidence_type": "pattern_hint", "system": "collision_system"},
        ],
        "runtime_corroboration": {},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.1},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["pattern_hints_without_semantic_code"]),
    }


@dataclass(frozen=True)
class StressCaseSpec:
    archetype: str
    layer_builder: LayerBuilder
    teacher_achieved: bool
    system_achieved: bool
    teacher_strength: str
    review_complexity: str
    stress_focus: List[str] = field(default_factory=list)
    teacher_notes: List[str] = field(default_factory=list)
    reviewer_taxonomy: List[str] = field(default_factory=list)


def _stress_catalog() -> List[StressCaseSpec]:
    """50 designed failure-oriented operational cases (not random cycling)."""

    def _c(
        archetype: str,
        builder: LayerBuilder,
        *,
        teacher: bool,
        system: bool,
        strength: str = "moderate",
        complexity: str = "moderate",
        focus: Optional[List[str]] = None,
        notes: Optional[List[str]] = None,
        tax: Optional[List[str]] = None,
    ) -> StressCaseSpec:
        return StressCaseSpec(
            archetype=archetype,
            layer_builder=builder,
            teacher_achieved=teacher,
            system_achieved=system,
            teacher_strength=strength,
            review_complexity=complexity,
            stress_focus=focus or [],
            teacher_notes=notes or [f"stress:{archetype}"],
            reviewer_taxonomy=tax or [],
        )

    return [
        _c("strong_corroboration", _layer_strong, teacher=True, system=True, strength="strong", complexity="easy",
           focus=["baseline", "review_gate_quiet"], tax=[]),
        _c("strong_corroboration", _layer_strong, teacher=True, system=True, strength="strong", complexity="easy",
           focus=["baseline_repeat"], tax=[]),
        _c("runtime_real_stacked", _layer_strong, teacher=True, system=True, strength="strong", complexity="easy",
           focus=["runtime_corroboration"], tax=[]),
        _c("runtime_fake_log_only", _layer_runtime_fake, teacher=False, system=True, strength="weak",
           focus=["runtime_without_system", "fp_risk"], tax=["stress_expected_fp"]),
        _c("runtime_fake_log_only", _layer_runtime_fake, teacher=False, system=True, strength="weak",
           focus=["fake_runtime"], tax=["stress_expected_fp"]),
        _c("runtime_fake_log_only", _layer_runtime_fake, teacher=False, system=True, strength="weak",
           focus=["fake_runtime_repeat"], tax=["stress_expected_fp"]),
        _c("screenshots_only", _layer_screenshots_only, teacher=False, system=True, strength="weak",
           focus=["screenshots_only", "sufficiency"], tax=["stress_expected_fp"]),
        _c("screenshots_only", _layer_screenshots_only, teacher=False, system=True, strength="weak",
           focus=["screenshots_only"], tax=["stress_expected_fp"]),
        _c("ocr_misleading_score100", _layer_ocr_misleading, teacher=False, system=True, strength="weak",
           focus=["ocr_inflation", "no_systems"], tax=["stress_expected_fp", "ocr_misleading"]),
        _c("ocr_misleading_score100", _layer_ocr_misleading, teacher=False, system=True, strength="weak",
           focus=["ocr_inflation"], tax=["stress_expected_fp"]),
        _c("ocr_misleading_score100", _layer_ocr_misleading, teacher=False, system=True, complexity="ambiguous",
           focus=["review_escalation_ocr"], tax=["stress_expected_fp"]),
        _c("logs_without_systems", _layer_runtime_fake, teacher=False, system=True, strength="weak",
           focus=["logs_without_systems"], tax=["stress_expected_fp"]),
        _c("logs_without_systems", _layer_runtime_fake, teacher=False, system=True,
           focus=["runtime_corroboration_gap"], tax=["stress_expected_fp"]),
        _c("systems_without_runtime", _layer_systems_no_runtime, teacher=False, system=True, strength="moderate",
           focus=["systems_without_runtime"], tax=["stress_expected_fp"]),
        _c("systems_without_runtime", _layer_systems_no_runtime, teacher=False, system=True,
           focus=["missing_runtime_corroboration"], tax=["stress_expected_fp"]),
        _c("systems_without_runtime", _layer_systems_no_runtime, teacher=False, system=True,
           focus=["code_only"], tax=["stress_expected_fp"]),
        _c("pattern_hints_only", _layer_pattern_only, teacher=False, system=True, strength="weak",
           focus=["pattern_hint_dependence"], tax=["stress_expected_fp"]),
        _c("pattern_hints_only", _layer_pattern_only, teacher=False, system=True,
           focus=["pattern_hints_only"], tax=["stress_expected_fp"]),
        _c("pattern_hints_only", _layer_pattern_only, teacher=False, system=True, complexity="ambiguous",
           focus=["review_gate_pattern"], tax=["stress_expected_fp"]),
        _c("noisy_upload_library_temp", _layer_noisy, teacher=False, system=False, strength="weak",
           focus=["submission_noise", "critical_review"], tax=[]),
        _c("noisy_upload_library_temp", _layer_noisy, teacher=False, system=False,
           focus=["intake_diagnostics", "review_inflation"], tax=[]),
        _c("noisy_upload_node_modules", _layer_noisy, teacher=False, system=False,
           focus=["excessive_submission_noise"], tax=[]),
        _c("corrupt_archive_sparse", _layer_corrupt_sparse, teacher=False, system=False, strength="weak",
           focus=["corrupt_zip", "sparse_evidence"], tax=[]),
        _c("corrupt_archive_sparse", _layer_corrupt_sparse, teacher=False, system=False,
           focus=["fp_empty_evidence_layer"], tax=[]),
        _c("weak_corroboration", _layer_weak_corroboration, teacher=False, system=True, strength="weak",
           focus=["weak_corroboration"], tax=["stress_expected_fp"]),
        _c("weak_corroboration", _layer_weak_corroboration, teacher=False, system=True,
           focus=["low_diversity"], tax=["stress_expected_fp"]),
        _c("cross_modal_conflict", _layer_cross_conflict, teacher=False, system=True, strength="moderate",
           focus=["cross_modal_conflicts"], tax=["stress_expected_fp"]),
        _c("cross_modal_conflict", _layer_cross_conflict, teacher=False, system=True,
           focus=["corroboration_conflict"], tax=["stress_expected_fp"]),
        _c("cross_modal_conflict", _layer_cross_conflict, teacher=False, system=True, complexity="ambiguous",
           focus=["severity_skew"], tax=["stress_expected_fp"]),
        _c("borderline_video_only_code", _layer_video_only_code, teacher=False, system=True, strength="moderate",
           focus=["collision_code_video_only", "sufficiency", "review_gates"],
           notes=["collision_system in code; video only; no log/screenshot"], tax=["stress_expected_fp"]),
        _c("borderline_video_only_code", _layer_video_only_code, teacher=False, system=True, complexity="ambiguous",
           focus=["borderline_sufficiency"], tax=["stress_expected_fp"]),
        _c("borderline_video_only_code", _layer_video_only_code, teacher=True, system=True, strength="moderate",
           complexity="ambiguous", focus=["borderline_teacher_yes_system_yes"],
           notes=["teacher accepts borderline; system also achieved — agreement stress"], tax=[]),
        _c("video_only_windows", _layer_video_only_windows, teacher=False, system=True,
           focus=["video_only_windows"], tax=["stress_expected_fp"]),
        _c("video_only_windows", _layer_video_only_windows, teacher=False, system=True,
           focus=["temporal_overlap"], tax=["stress_expected_fp"]),
        _c("ocr_video_without_corroboration", _layer_ocr_video_no_corr, teacher=False, system=True,
           focus=["ocr_video_without_corroboration"], tax=["stress_expected_fp"]),
        _c("ocr_video_without_corroboration", _layer_ocr_video_no_corr, teacher=False, system=True,
           focus=["cross_modal_false_overlap"], tax=["stress_expected_fp"]),
        _c("sparse_evidence_empty", _layer_corrupt_sparse, teacher=False, system=False, strength="weak",
           focus=["sparse_evidence"], tax=[]),
        _c("sparse_evidence_empty", _layer_corrupt_sparse, teacher=False, system=False,
           focus=["minimal_items"], tax=[]),
        _c("fake_runtime_fp_system", _layer_runtime_fake, teacher=False, system=True,
           focus=["fp_driver_fake_runtime"], tax=["confirmed_fp_stress"]),
        _c("fake_runtime_fp_system", _layer_runtime_fake, teacher=False, system=True,
           tax=["confirmed_fp_stress"]),
        _c("achievement_inflation_weak_code", _layer_inflation_weak_code, teacher=False, system=True,
           focus=["pattern_hint_dependence", "weak_code"], tax=["stress_expected_fp"]),
        _c("achievement_inflation_weak_code", _layer_inflation_weak_code, teacher=False, system=True,
           tax=["stress_expected_fp"]),
        _c("fn_control_teacher_yes_system_no", _layer_borderline_near_pass, teacher=True, system=False,
           strength="moderate", focus=["fn_control"], tax=["stress_expected_fn"]),
        _c("fn_control_teacher_yes_system_no", _layer_strong, teacher=True, system=False,
           focus=["fn_control_strong"], tax=["stress_expected_fn"]),
        _c("borderline_sufficiency_near_pass", _layer_borderline_near_pass, teacher=True, system=True,
           complexity="ambiguous", focus=["borderline_sufficiency"], tax=[]),
        _c("borderline_sufficiency_near_pass", _layer_borderline_near_pass, teacher=False, system=True,
           complexity="ambiguous", focus=["borderline_fp"], tax=["stress_expected_fp"]),
        _c("cross_modal_false_overlap", _layer_false_overlap, teacher=False, system=True,
           focus=["fake_corroboration"], tax=["stress_expected_fp"]),
        _c("runtime_stale_no_temporal", _layer_runtime_stale, teacher=False, system=True,
           focus=["temporal_misalignment"], tax=["stress_expected_fp"]),
        _c("strong_corroboration_control", _layer_strong, teacher=True, system=True, strength="strong",
           complexity="easy", focus=["control_no_fp"], tax=[]),
        _c("noisy_upload_critical_combo", _layer_noisy, teacher=False, system=False,
           focus=["review_gate_inflation", "critical_severity"], tax=[]),
        _c("runtime_real_stacked", _layer_strong, teacher=True, system=True,
           focus=["strong_corroboration_repeat"], tax=[]),
        _c("logs_without_systems", _layer_runtime_fake, teacher=False, system=False,
           focus=["tn_system_conservative"], tax=[]),
        _c("pattern_hints_only", _layer_pattern_only, teacher=False, system=False,
           focus=["tn_conservative_pattern"], tax=[]),
    ]


def _items_from_layer(layer: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [dict(it) for it in (layer.get("items") or []) if isinstance(it, dict)]


def _build_snapshot(spec: StressCaseSpec) -> Dict[str, Any]:
    from app.project_intelligence.evidence_schema import build_evidence_layer_from_profile
    from app.project_intelligence.human_review_gates import attach_human_review_gates
    from app.project_intelligence.project_profile import build_project_profile
    from app.project_intelligence.rubric_sufficiency_contracts import attach_rubric_sufficiency_shadow

    layer = spec.layer_builder()
    paths = [f"/stress/{spec.archetype}/marker.txt"]
    profile = build_project_profile(paths)
    ev_layer = build_evidence_layer_from_profile(profile)
    ev_layer["items"] = _items_from_layer(layer)
    for key in (
        "runtime_corroboration",
        "cross_modal_corroboration",
        "submission_intake",
        "rubric_sufficiency_shadow",
    ):
        if layer.get(key):
            ev_layer[key] = layer[key]

    grading_stub = {
        "criteria_results": [
            {
                "criteria_level": "A.P3",
                "achieved": spec.system_achieved,
                "reasoning": "reliability stress cohort — LLM slice not exercised",
            }
        ]
    }
    attach_rubric_sufficiency_shadow(grading_stub, ev_layer, profile=profile)
    attach_human_review_gates(grading_stub, ev_layer)

    cr = grading_stub["criteria_results"][0]
    return {
        "criteria_results": [cr],
        "evidence_layer": ev_layer,
        "assessment_trace": {
            "rubric_version": "stress_cohort",
            "calibration_run_id": "reliability_stress",
            "stress_archetype": spec.archetype,
        },
    }


def generate_stress_cohort(count: int = 50) -> tuple[Dict[str, Any], Dict[str, Any]]:
    catalog = _stress_catalog()
    if count > len(catalog):
        raise ValueError(f"stress catalog has {len(catalog)} cases; requested {count}")
    selected = catalog[:count]

    records: List[Dict[str, Any]] = []
    submissions: Dict[str, Any] = {}

    for i, spec in enumerate(selected):
        arch = spec.archetype
        sid = f"STRESS_{i:03d}_{arch}"
        crit = "P3"
        snap = _build_snapshot(spec)
        submissions[sid] = snap

        tax = list(spec.reviewer_taxonomy)
        if not spec.teacher_achieved and spec.system_achieved:
            if "stress_expected_fp" in tax or "confirmed_fp_stress" in tax:
                pass
            elif spec.system_achieved:
                tax.append("stress_fp_candidate")
        if spec.teacher_achieved and not spec.system_achieved:
            tax.append("stress_fn_candidate")

        records.append(
            {
                "submission_id": sid,
                "unit": "STRESS_Unit_GameDev",
                "criterion": crit,
                "submission_archetype": arch,
                "cohort_tags": ["reliability_stress", arch] + spec.stress_focus[:3],
                "stress_focus": spec.stress_focus,
                "teacher_result": {"achieved": spec.teacher_achieved, "confidence": 0.9},
                "teacher_evidence_strength": spec.teacher_strength,
                "review_complexity": spec.review_complexity,
                "reviewer_taxonomy": tax,
                "teacher_notes": spec.teacher_notes,
                "accepted_evidence": ["stress_accepted"] if spec.teacher_achieved else [],
                "rejected_evidence": ["stress_rejected"] if not spec.teacher_achieved else [],
            }
        )

    gold_doc = {
        "schema": "unity_calibration_gold_v2",
        "synthetic": True,
        "stress_cohort": True,
        "description": (
            "Reliability Stress Cohort — failure-oriented operational simulation. "
            "NOT teacher ground truth or production validation."
        ),
        "target_count": count,
        "records": records,
    }
    sys_doc = {
        "schema": "system_snapshots_export_v1",
        "synthetic": True,
        "stress_cohort": True,
        "submission_count": len(submissions),
        "submissions": submissions,
    }
    return gold_doc, sys_doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate reliability stress cohort (failure-oriented)")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--out-dir", type=Path, default=Path("app/calibration/gold_dataset"))
    args = ap.parse_args()

    catalog_len = len(_stress_catalog())
    if args.count < 1 or args.count > catalog_len:
        print(f"count must be 1..{catalog_len} (designed cases)", file=sys.stderr)
        return 1

    gold, systems = generate_stress_cohort(args.count)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    gold_path = args.out_dir / "unity_gold_reliability_stress_v1.json"
    sys_path = args.out_dir / "system_snapshots_reliability_stress_v1.json"
    gold_path.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    sys_path.write_text(json.dumps(systems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {gold_path} ({len(gold['records'])} records)")
    print(f"Wrote {sys_path} ({systems['submission_count']} submissions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
