"""
Governance rehearsal cohort — synthetic disagreement-oriented cases (NOT perfect datasets).

25 cases (5 per layer): clear, partial_sufficiency, false_confidence, disagreement, hold_expected.

Purpose: stress-test governance behaviour (HOLD, corroboration, sufficiency shadow, advisory-only).
NOT AI benchmark / NOT production validation.

Usage:
  python -m app.calibration.generate_disagreement_cohort
  python -m app.calibration.generate_disagreement_cohort --write-tree
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.calibration.generate_reliability_stress_cohort import (
    StressCaseSpec,
    _build_snapshot,
    _layer_corrupt_sparse,
    _layer_inflation_weak_code,
    _layer_ocr_misleading,
    _layer_pattern_only,
    _layer_screenshots_only,
    _layer_strong,
    _layer_systems_no_runtime,
    _layer_video_only_code,
    _layer_weak_corroboration,
)

LayerBuilder = Callable[[], Dict[str, Any]]


@dataclass(frozen=True)
class DisagreementCaseSpec:
    archetype: str
    layer_builder: LayerBuilder
    teacher_achieved: bool
    system_achieved: bool
    teacher_strength: str
    review_complexity: str
    cohort_layer: str
    case_metadata: Dict[str, Any] = field(default_factory=dict)
    stress_focus: List[str] = field(default_factory=list)
    teacher_notes: List[str] = field(default_factory=list)
    reviewer_taxonomy: List[str] = field(default_factory=list)


def _meta(
    *,
    layer: str,
    expected_ambiguity: str,
    intended_disagreement: bool,
    evidence_completeness: str,
    fake_confidence_risk: str,
    expected_governance: List[str],
    assessor_split_note: str = "",
) -> Dict[str, Any]:
    return {
        "cohort_layer": layer,
        "governance_rehearsal": True,
        "not_ai_benchmark": True,
        "expected_ambiguity": expected_ambiguity,
        "intended_disagreement": intended_disagreement,
        "evidence_completeness": evidence_completeness,
        "fake_confidence_risk": fake_confidence_risk,
        "expected_governance_behaviour": expected_governance,
        "assessor_split_note": assessor_split_note,
        "evaluate": [
            "uncertainty_visible",
            "hold_when_expected",
            "corroboration_pressure",
            "advisory_stays_advisory",
            "explanation_auditable",
        ],
    }


def _disagreement_catalog() -> List[DisagreementCaseSpec]:
    def _d(
        layer: str,
        archetype: str,
        builder: LayerBuilder,
        *,
        teacher: bool,
        system: bool,
        meta: Dict[str, Any],
        strength: str = "moderate",
        complexity: str = "moderate",
        notes: Optional[List[str]] = None,
        tax: Optional[List[str]] = None,
    ) -> DisagreementCaseSpec:
        return DisagreementCaseSpec(
            archetype=archetype,
            layer_builder=builder,
            teacher_achieved=teacher,
            system_achieved=system,
            teacher_strength=strength,
            review_complexity=complexity,
            stress_focus=meta.get("expected_governance_behaviour", [])[:3],
            teacher_notes=notes or [f"governance_rehearsal:{layer}:{archetype}"],
            reviewer_taxonomy=tax or [],
            cohort_layer=layer,
            case_metadata=meta,
        )

    cases: List[DisagreementCaseSpec] = []

    # --- 1. clear_pass (5) — sanity, no spurious HOLD ---
    for i, arch in enumerate(
        ["python_neat", "docs_clear", "screenshots_match", "code_and_log", "balanced_evidence"], 1
    ):
        cases.append(
            _d(
                "clear_pass_cases",
                arch,
                _layer_strong,
                teacher=True,
                system=True,
                strength="strong",
                complexity="easy",
                meta=_meta(
                    layer="clear_pass_cases",
                    expected_ambiguity="low",
                    intended_disagreement=False,
                    evidence_completeness="high",
                    fake_confidence_risk="low",
                    expected_governance=[
                        "no_spurious_hold",
                        "no_invented_evidence",
                        "moderate_or_low_review",
                    ],
                ),
            )
        )

    # --- 2. partial_sufficiency (5) ---
    partial_specs = [
        ("code_no_runtime", _layer_systems_no_runtime, False, True, "medium", "moderate"),
        ("video_only", _layer_video_only_code, False, True, "low", "ambiguous"),
        ("weak_corroboration", _layer_weak_corroboration, False, True, "medium", "moderate"),
        ("borderline_near", _layer_strong, True, True, "medium", "ambiguous"),
        ("screenshots_partial", _layer_screenshots_only, False, True, "low", "moderate"),
    ]
    for arch, builder, t, s, comp, amb in partial_specs:
        cases.append(
            _d(
                "partial_sufficiency",
                arch,
                builder,
                teacher=t,
                system=s,
                strength="moderate",
                complexity=amb,
                meta=_meta(
                    layer="partial_sufficiency",
                    expected_ambiguity=amb,
                    intended_disagreement=False,
                    evidence_completeness=comp,
                    fake_confidence_risk="medium",
                    expected_governance=[
                        "sufficiency_shadow_insufficient",
                        "review_escalation_possible",
                        "achieved_not_from_shadow",
                    ],
                ),
            )
        )

    # --- 3. false_confidence (5) ---
    false_specs = [
        ("ocr_score_100", _layer_ocr_misleading),
        ("doc_style_no_code", _layer_pattern_only),
        ("weak_code_hints", _layer_inflation_weak_code),
        ("ocr_repeat", _layer_ocr_misleading),
        ("pattern_screenshots", _layer_screenshots_only),
    ]
    for arch, builder in false_specs:
        cases.append(
            _d(
                "false_confidence",
                arch,
                builder,
                teacher=False,
                system=True,
                strength="weak",
                complexity="ambiguous",
                meta=_meta(
                    layer="false_confidence",
                    expected_ambiguity="high",
                    intended_disagreement=False,
                    evidence_completeness="low",
                    fake_confidence_risk="high",
                    expected_governance=[
                        "corroboration_pressure",
                        "pattern_or_ocr_not_sufficient_alone",
                        "fp_risk_if_system_achieved",
                    ],
                ),
                tax=["rehearsal_false_confidence"],
            )
        )

    # --- 4. disagreement (5) — assessor split in metadata ---
    disagreement_specs = [
        (
            "ui_functionality_borderline",
            _layer_video_only_code,
            True,
            True,
            "Assessor A may accept UI/video; Assessor B wants runtime log",
        ),
        (
            "pseudo_code_debate",
            _layer_pattern_only,
            False,
            True,
            "Some assessors accept pattern hints; others reject without code_system",
        ),
        (
            "partial_testing_debate",
            _layer_weak_corroboration,
            True,
            False,
            "Teacher yes on partial test matrix; system conservative no",
        ),
        (
            "borderline_teacher_no_system_yes",
            _layer_systems_no_runtime,
            False,
            True,
            "Classic FP rehearsal: code present, runtime missing",
        ),
        (
            "ambiguous_both_borderline",
            _layer_video_only_code,
            False,
            False,
            "Both assessors uncertain; neither strong pass",
        ),
    ]
    for arch, builder, t, s, split_note in disagreement_specs:
        cases.append(
            _d(
                "disagreement_cases",
                arch,
                builder,
                teacher=t,
                system=s,
                complexity="ambiguous",
                meta=_meta(
                    layer="disagreement_cases",
                    expected_ambiguity="high",
                    intended_disagreement=True,
                    evidence_completeness="medium",
                    fake_confidence_risk="medium",
                    expected_governance=[
                        "human_review_likely",
                        "taxonomy_ambiguous",
                        "no_automatic_authority",
                    ],
                    assessor_split_note=split_note,
                ),
            )
        )

    # --- 5. hold_expected (5) ---
    hold_specs = [
        ("corrupt_zip", _layer_corrupt_sparse, False, False),
        ("screenshots_only_fail", _layer_screenshots_only, False, False),
        ("pattern_only_fail", _layer_pattern_only, False, False),
        ("empty_submission", _layer_corrupt_sparse, False, False),
        ("sparse_noise", _layer_corrupt_sparse, False, False),
    ]
    for arch, builder, t, s in hold_specs:
        cases.append(
            _d(
                "hold_expected",
                arch,
                builder,
                teacher=t,
                system=s,
                strength="weak",
                complexity="moderate",
                meta=_meta(
                    layer="hold_expected",
                    expected_ambiguity="medium",
                    intended_disagreement=False,
                    evidence_completeness="low",
                    fake_confidence_risk="low",
                    expected_governance=[
                        "human_review_or_conservative_achieved",
                        "insufficiency_clear",
                        "reject_overclaim",
                    ],
                ),
            )
        )

    return cases


def generate_disagreement_cohort() -> tuple[Dict[str, Any], Dict[str, Any], List[DisagreementCaseSpec]]:
    catalog = _disagreement_catalog()
    records: List[Dict[str, Any]] = []
    submissions: Dict[str, Any] = {}

    for i, spec in enumerate(catalog):
        layer = spec.cohort_layer
        sid = f"GOV_{i:03d}_{layer}_{spec.archetype}"
        stress_spec = StressCaseSpec(
            archetype=spec.archetype,
            layer_builder=spec.layer_builder,
            teacher_achieved=spec.teacher_achieved,
            system_achieved=spec.system_achieved,
            teacher_strength=spec.teacher_strength,
            review_complexity=spec.review_complexity,
            stress_focus=spec.stress_focus,
            teacher_notes=spec.teacher_notes,
            reviewer_taxonomy=spec.reviewer_taxonomy,
        )
        snap = _build_snapshot(stress_spec)
        snap["assessment_trace"]["cohort_layer"] = layer
        snap["assessment_trace"]["case_metadata"] = spec.case_metadata
        submissions[sid] = snap

        records.append(
            {
                "submission_id": sid,
                "unit": "GOV_REHEARSAL_Unit",
                "criterion": "P3",
                "submission_archetype": spec.archetype,
                "cohort_tags": ["governance_rehearsal", layer, spec.archetype],
                "cohort_layer": layer,
                "case_metadata": spec.case_metadata,
                "teacher_result": {"achieved": spec.teacher_achieved, "confidence": 0.88},
                "teacher_evidence_strength": spec.teacher_strength,
                "review_complexity": spec.review_complexity,
                "reviewer_taxonomy": list(spec.reviewer_taxonomy),
                "teacher_notes": spec.teacher_notes,
                "accepted_evidence": ["rehearsal_accepted"] if spec.teacher_achieved else [],
                "rejected_evidence": ["rehearsal_rejected"] if not spec.teacher_achieved else [],
            }
        )

    gold_doc = {
        "schema": "unity_calibration_gold_v2",
        "synthetic": True,
        "governance_rehearsal": True,
        "disagreement_oriented": True,
        "description": (
            "Governance rehearsal cohort — messy educational reality simulation. "
            "NOT perfect datasets; NOT production validation."
        ),
        "target_count": len(catalog),
        "layers": {
            "clear_pass_cases": 5,
            "partial_sufficiency": 5,
            "false_confidence": 5,
            "disagreement_cases": 5,
            "hold_expected": 5,
        },
        "records": records,
    }
    sys_doc = {
        "schema": "system_snapshots_export_v1",
        "synthetic": True,
        "governance_rehearsal": True,
        "submission_count": len(submissions),
        "submissions": submissions,
    }
    return gold_doc, sys_doc, catalog


def _write_cohort_tree(base: Path, catalog: List[DisagreementCaseSpec]) -> None:
    layer_dirs = {
        "clear_pass_cases",
        "partial_sufficiency",
        "false_confidence",
        "disagreement_cases",
        "hold_expected",
    }
    for name in layer_dirs:
        (base / name).mkdir(parents=True, exist_ok=True)

    for i, spec in enumerate(catalog):
        layer = spec.cohort_layer
        case_dir = base / layer / f"{i:03d}_{spec.archetype}"
        case_dir.mkdir(parents=True, exist_ok=True)
        meta_path = case_dir / "case_metadata.json"
        meta_path.write_text(
            json.dumps(spec.case_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate disagreement-oriented governance rehearsal cohort")
    ap.add_argument("--out-dir", type=Path, default=Path("app/calibration/gold_dataset"))
    ap.add_argument(
        "--tree-dir",
        type=Path,
        default=Path("app/calibration/synthetic_cohorts"),
        help="Folder tree for case_metadata.json per case",
    )
    ap.add_argument("--write-tree", action="store_true")
    args = ap.parse_args()

    gold, systems, catalog = generate_disagreement_cohort()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    gold_path = args.out_dir / "unity_gold_disagreement_rehearsal_v1.json"
    sys_path = args.out_dir / "system_snapshots_disagreement_rehearsal_v1.json"
    gold_path.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    sys_path.write_text(json.dumps(systems, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.write_tree:
        _write_cohort_tree(args.tree_dir, catalog)
        readme = args.tree_dir / "README.md"
        readme.write_text(
            "# Synthetic disagreement-oriented cohorts\n\n"
            "Governance rehearsal — not AI benchmark.\n\n"
            "Layers: `clear_pass_cases`, `partial_sufficiency`, `false_confidence`, "
            "`disagreement_cases`, `hold_expected` (5 each).\n\n"
            "Generate: `python -m app.calibration.generate_disagreement_cohort --write-tree`\n",
            encoding="utf-8",
        )

    print(f"Wrote {gold_path} ({len(gold['records'])} records)")
    print(f"Wrote {sys_path}")
    if args.write_tree:
        print(f"Wrote tree under {args.tree_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
