"""
Synthetic evidence_layer fixtures for human review gates (advisory only).

Usage (repo root):
  python -m app.calibration.mini_validation_human_review.run_mini_validation_human_review
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


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


def _layer_a() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
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
        "runtime_corroboration": {
            "by_system": {
                "collision_system": {
                    "corroboration_modalities": ["code_system", "runtime_log", "runtime_screenshot"],
                    "corroboration_strength": "medium",
                }
            },
            "corroboration_conflicts": [],
            "missing_runtime_corroboration_flags": [],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.75,
            "cross_modal_noise_flags": [],
        },
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(True, []),
    }


def _layer_b() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
        ],
        "runtime_corroboration": {
            "by_system": {},
            "corroboration_conflicts": [],
            "missing_runtime_corroboration_flags": [
                {"flag": "collision_system_detected_without_runtime_signal", "system": "collision_system"}
            ],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.25,
            "cross_modal_noise_flags": [],
        },
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(
            False, ["runtime_present_without_system_confirmation"]
        ),
    }


def _layer_c() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [{"evidence_type": "pattern_hint", "system": "collision_system"}],
        "runtime_corroboration": {"corroboration_conflicts": []},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.0},
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["pattern_hints_only_insufficient"]),
    }


def _layer_d() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.75,
                "execution_evidence": "medium",
            },
            {"evidence_type": "runtime_log", "log_signals": {"mentions_collision": True}},
        ],
        "runtime_corroboration": {
            "corroboration_conflicts": [
                {"flag": "runtime_log_present_without_matching_system", "mention_key": "mentions_scene"},
                {"flag": "system_detected_without_any_runtime_artifact", "system": "ui_system"},
            ],
            "missing_runtime_corroboration_flags": [],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.5,
            "cross_modal_noise_flags": [],
        },
        "submission_intake": {"submission_noise_flags": []},
        "rubric_sufficiency_shadow": _shadow(False, ["corroboration_conflict_detected"]),
    }


def _layer_e() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [{"evidence_type": "pattern_hint", "system": "collision_system"}],
        "runtime_corroboration": {"corroboration_conflicts": []},
        "cross_modal_corroboration": {"cross_modal_diversity_score": 0.0},
        "submission_intake": {
            "submission_noise_flags": [
                {"flag": "unity_library_folder_uploaded"},
                {"flag": "node_modules_folder_uploaded"},
                {"flag": "git_folder_uploaded"},
                {"flag": "build_artifact_path_uploaded"},
                {"flag": "engine_temp_or_tmp_uploaded"},
            ],
            "upload_diagnostics": {"ignore_ratio": 0.52, "ignored_files": 120, "total_files_uploaded": 230},
        },
        "rubric_sufficiency_shadow": _shadow(False, ["pattern_hints_only_insufficient"]),
    }


_FIXTURES = {
    "case_a_strong_no_review": _layer_a,
    "case_b_runtime_no_corroboration": _layer_b,
    "case_c_pattern_hints_only": _layer_c,
    "case_d_cross_modal_conflict": _layer_d,
    "case_e_sparse_noise_critical": _layer_e,
}


def _compact(ev: Dict[str, Any]) -> Dict[str, Any]:
    hr = ev.get("human_review_required") or {}
    return {
        "required": hr.get("required"),
        "severity": hr.get("severity"),
        "reasons": hr.get("reasons"),
        "review_confidence": ev.get("review_confidence"),
        "review_categories": ev.get("review_categories"),
        "review_reasoning": (ev.get("review_reasoning") or {}).get("reasoning"),
        "triggers_fired": [t.get("trigger_id") for t in (ev.get("triggers_fired") or [])],
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))

    from app.project_intelligence.human_review_gates import (
        build_evidence_layer_human_review,
        evaluate_human_review_gates,
    )

    cases_out: List[Dict[str, Any]] = []
    for entry in template.get("cases") or []:
        cid = entry.get("case_id") or ""
        builder = _FIXTURES.get(cid)
        if not builder:
            cases_out.append({**entry, "actual_behavior": json.dumps({"error": f"no_fixture:{cid}"})})
            continue
        layer = builder()
        submission_eval = evaluate_human_review_gates(layer)
        block = build_evidence_layer_human_review(layer)
        snap = {
            "submission": _compact(submission_eval),
            "layer_block_submission": (block.get("submission") or {}),
            "criterion_A.P3": _compact((block.get("by_criterion") or {}).get("A.P3") or {}),
        }
        cases_out.append(
            {**entry, "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2)}
        )

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "Advisory only. Fill observed_friction after manual review.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_human_review_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by = {c.get("case_id"): c for c in prev.get("cases") or []}
        for row in out.get("cases") or []:
            cid = row.get("case_id")
            if cid in prev_by:
                for key in ("observed_friction", "unexpected_result", "observation_notes"):
                    if prev_by[cid].get(key):
                        row[key] = prev_by[cid][key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
