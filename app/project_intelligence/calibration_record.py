"""
Gold dataset / calibration — structural contract only (no DB migration here).

Export rows matching this shape from lab tooling or a future `calibration_exports`
table. Keeps teacher truth, deterministic evidence, shadow rubric, and LLM slice
comparable for precision/recall work.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GoldDatasetRowV01(TypedDict, total=False):
    submission_id: Optional[str]
    unit: Optional[str]
    criterion: Optional[str]
    assignment_ref: Optional[str]
    rubric_version: str
    teacher_result: Dict[str, Any]
    teacher_evidence_strength: str  # weak | moderate | strong
    review_complexity: str  # easy | moderate | ambiguous
    reviewer_taxonomy: List[str]
    evidence_layer: Dict[str, Any]
    rubric_shadow_result: Dict[str, Any]
    llm_result: Dict[str, Any]
    final_result: Dict[str, Any]
    assessor_agreement: List[str]
    teacher_notes: List[str]
    accepted_evidence: List[str]
    rejected_evidence: List[str]
    notes: str
