"""
Versioning + trace metadata for institutional audit and offline re-grading.

Keeps a record of which rubric / schema versions produced a grading_snapshot so
historical re-evaluation and appeals remain interpretable after thresholds change.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional


def build_assessment_trace(
    evidence_layer: Optional[Dict[str, Any]],
    project_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    from app.project_intelligence.evidence_requirement_graph import GRAPH_SCHEMA_VERSION
    from app.project_intelligence.human_review_gates import HUMAN_REVIEW_GATES_VERSION
    from app.project_intelligence.rubric_sufficiency_contracts import RUBRIC_SUFFICIENCY_VERSION

    rv = (os.getenv("RUBRIC_VERSION") or "unversioned").strip()
    cr = (os.getenv("CALIBRATION_RUN_ID") or "").strip() or None

    return {
        "rubric_version": rv,
        "evidence_schema_version": (evidence_layer or {}).get("schema_version"),
        "evidence_requirement_graph_version": GRAPH_SCHEMA_VERSION,
        "rubric_sufficiency_contracts_version": RUBRIC_SUFFICIENCY_VERSION,
        "human_review_gates_version": HUMAN_REVIEW_GATES_VERSION,
        "human_review_advisory_mode": "governance_signal_only",
        "project_profile_version": (project_profile or {}).get("version"),
        "calibration_run_id": cr,
        # Reserved for shadow / gold pipeline — fill when exporting calibration bundles
        "rubric_shadow_eval_enabled": os.getenv("RUBRIC_SHADOW_EVAL", "").strip().lower()
        in ("1", "true", "yes", "on"),
    }
