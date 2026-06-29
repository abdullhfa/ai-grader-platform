"""
Synthetic evidence_layer fixtures for rubric sufficiency shadow (observation only).

Usage (repo root):
  python -m app.calibration.mini_validation_rubric_sufficiency.run_mini_validation_rubric_sufficiency
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _layer_case_a() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.85,
                "execution_evidence": "medium",
            },
            {
                "evidence_type": "runtime_log",
                "system": None,
                "log_signals": {"mentions_collision": True, "line_count": 12},
            },
            {"evidence_type": "runtime_screenshot", "sources": ["cap.png"]},
            {"evidence_type": "video_frame", "sources": ["f1.png"]},
        ],
        "runtime_corroboration": {
            "by_system": {
                "collision_system": {
                    "corroboration_modalities": [
                        "code_system",
                        "runtime_log",
                        "runtime_screenshot",
                    ],
                    "modality_diversity_score": 0.67,
                    "weighted_corroboration_score": 0.8,
                    "corroboration_strength": "medium",
                }
            },
            "corroboration_conflicts": [],
            "missing_runtime_corroboration_flags": [],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.5,
            "cross_modal_noise_flags": [],
        },
    }


def _layer_case_b() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "runtime_log",
                "log_signals": {"mentions_collision": True, "line_count": 8},
            },
        ],
        "runtime_corroboration": {
            "by_system": {},
            "corroboration_conflicts": [],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.25,
            "cross_modal_noise_flags": [],
        },
    }


def _layer_case_c() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "pattern_hint",
                "system": "collision_system",
                "confidence": None,
            },
        ],
        "runtime_corroboration": {"by_system": {}, "corroboration_conflicts": []},
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.0,
            "cross_modal_noise_flags": [],
        },
    }


def _layer_case_d() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {"evidence_type": "video_frame", "sources": ["v1.png"]},
            {"evidence_type": "ocr_text", "raw_text": "score 100"},
        ],
        "runtime_corroboration": {"by_system": {}, "corroboration_conflicts": []},
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.25,
            "cross_modal_noise_flags": [],
        },
    }


def _layer_case_e() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "items": [
            {
                "evidence_type": "code_system",
                "system": "collision_system",
                "confidence": 0.6,
                "execution_evidence": "weak",
            },
            {
                "evidence_type": "runtime_log",
                "log_signals": {"mentions_collision": True},
            },
        ],
        "runtime_corroboration": {
            "by_system": {
                "collision_system": {
                    "corroboration_modalities": ["code_system", "runtime_log"],
                    "modality_diversity_score": 0.5,
                }
            },
            "corroboration_conflicts": [
                {
                    "flag": "runtime_log_present_without_matching_system",
                    "mention_key": "mentions_scene",
                },
                {
                    "flag": "system_detected_without_any_runtime_artifact",
                    "system": "ui_system",
                },
            ],
        },
        "cross_modal_corroboration": {
            "cross_modal_diversity_score": 0.5,
            "cross_modal_noise_flags": [],
        },
    }


_FIXTURES = {
    "case_a_full_compatible": _layer_case_a,
    "case_b_runtime_without_system": _layer_case_b,
    "case_c_pattern_hints_only": _layer_case_c,
    "case_d_ocr_video_no_corroboration": _layer_case_d,
    "case_e_conflicting_evidence": _layer_case_e,
}


def _compact(shadow: Dict[str, Any]) -> Dict[str, Any]:
    sr = shadow.get("sufficiency_result") or {}
    return {
        "contract_id": shadow.get("contract_id"),
        "shadow_mode": shadow.get("shadow_mode"),
        "sufficient": sr.get("sufficient"),
        "required_evidence_satisfied": sr.get("required_evidence_satisfied"),
        "supporting_evidence_count": sr.get("supporting_evidence_count"),
        "missing_evidence": sr.get("missing_evidence"),
        "rejected_evidence_count": len(sr.get("rejected_evidence") or []),
        "modality_count": sr.get("modality_count"),
        "cross_modal_diversity_score": sr.get("cross_modal_diversity_score"),
        "sufficiency_reasoning": (shadow.get("sufficiency_reasoning") or {}).get("reasoning"),
        "insufficiency_flags": shadow.get("insufficiency_flags"),
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))

    from app.project_intelligence.rubric_sufficiency_contracts import (
        contract_game_collision_p3,
        evaluate_criterion_sufficiency,
    )

    contract = contract_game_collision_p3()
    cases_out: List[Dict[str, Any]] = []

    for entry in template.get("cases") or []:
        cid = entry.get("case_id") or ""
        builder = _FIXTURES.get(cid)
        if not builder:
            cases_out.append(
                {
                    **entry,
                    "actual_behavior": json.dumps({"error": f"no_fixture:{cid}"}),
                }
            )
            continue
        layer = builder()
        shadow = evaluate_criterion_sufficiency(layer, contract)
        cases_out.append(
            {
                **entry,
                "actual_behavior": json.dumps(_compact(shadow), ensure_ascii=False, indent=2),
            }
        )

    return {
        "run_purpose": template.get("run_purpose", ""),
        "contract_id": template.get("contract_id"),
        "cases": cases_out,
        "note": "Shadow only — achieved unchanged. Fill observed_friction after review.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_rubric_sufficiency_last_run.json"
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
