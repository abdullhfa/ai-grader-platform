"""Project structure analysis for BTEC submissions (Phase 1: detection + profile JSON)."""

from .evidence_requirement_graph import (
    evaluate_criterion_evidence_sufficiency,
    example_spec_collision_p3,
)
from .human_review_gates import (
    attach_human_review_gates,
    build_evidence_layer_human_review,
    evaluate_human_review_gates,
)
from .rubric_sufficiency_contracts import (
    attach_rubric_sufficiency_shadow,
    build_rubric_shadow_result,
    contract_game_collision_p3,
    evaluate_criterion_sufficiency,
    get_contract_registry,
    resolve_contract_for_criterion,
)
from .project_profile import (
    build_project_profile,
    format_profile_for_grading_prompt,
)
from .unity_extractor import analyze_unity_submission

__all__ = [
    "build_project_profile",
    "format_profile_for_grading_prompt",
    "analyze_unity_submission",
    "evaluate_criterion_evidence_sufficiency",
    "example_spec_collision_p3",
    "attach_human_review_gates",
    "attach_rubric_sufficiency_shadow",
    "build_evidence_layer_human_review",
    "evaluate_human_review_gates",
    "build_rubric_shadow_result",
    "contract_game_collision_p3",
    "evaluate_criterion_sufficiency",
    "get_contract_registry",
    "resolve_contract_for_criterion",
]
