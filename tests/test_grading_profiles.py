"""Tests for STANDARD/PRO grading mode profiles and governance invariance."""
from __future__ import annotations

from app.core.grading_context import SubmissionProcessingContext
from app.core.grading_profiles import (
    PRO_PROFILE,
    STANDARD_PROFILE,
    attach_grading_mode_metadata,
    resolve_grading_profile,
)
from app.grading_mode import GradingMode
from app.grading_mode_policy import normalize_grading_mode_choice
from app.runtime_evidence_gate import apply_runtime_evidence_gate


def test_grading_mode_wire_aliases():
    assert GradingMode.from_wire("standard") is GradingMode.STANDARD
    assert GradingMode.from_wire("fast") is GradingMode.STANDARD
    assert GradingMode.from_wire("basic") is GradingMode.STANDARD
    assert GradingMode.from_wire("pro") is GradingMode.PRO
    assert GradingMode.from_wire("deep") is GradingMode.PRO
    assert GradingMode.STANDARD.to_wire() == "fast"
    assert GradingMode.PRO.to_wire() == "deep"
    assert normalize_grading_mode_choice("standard") == "fast"
    assert normalize_grading_mode_choice("pro") == "deep"


def test_profile_selection():
    std = resolve_grading_profile("standard")
    pro = resolve_grading_profile("deep")
    assert std.mode is GradingMode.STANDARD
    assert pro.mode is GradingMode.PRO
    assert std.evidence_depth == "summary"
    assert pro.evidence_depth == "detailed"
    assert std is STANDARD_PROFILE
    assert pro is PRO_PROFILE


def test_standard_skips_gameplay_agent_pro_enables():
    assert STANDARD_PROFILE.gameplay_agent is False
    assert PRO_PROFILE.gameplay_agent is True
    assert STANDARD_PROFILE.ai_reasoning is False
    assert PRO_PROFILE.ai_reasoning is True
    assert STANDARD_PROFILE.runtime_enabled is True
    assert PRO_PROFILE.runtime_enabled is True


def test_standard_enables_fast_runtime_not_agent():
    std = SubmissionProcessingContext.from_wire("standard")
    assert std.grading_mode is GradingMode.STANDARD
    assert std.flags["skip_runtime_observation"] is False
    assert std.flags.get("fast_runtime_smoke") is True
    assert std.profile.runtime_enabled is True
    assert std.profile.gameplay_agent is False
    assert std.profile.ai_reasoning is False


def test_pro_enables_deep_runtime_and_agent():
    pro = SubmissionProcessingContext.from_wire("pro")
    assert pro.flags["skip_runtime_observation"] is False
    assert pro.profile.gameplay_agent is True
    assert pro.profile.runtime_depth == "deep"


def test_fast_runtime_screenshot_offsets():
    from app.runtime_observation_sandbox import (
        FAST_RUNTIME_SCREENSHOT_OFFSETS,
        RUNTIME_SCREENSHOT_OFFSETS,
        resolve_runtime_screenshot_offsets,
    )

    assert resolve_runtime_screenshot_offsets("fast") == FAST_RUNTIME_SCREENSHOT_OFFSETS
    assert resolve_runtime_screenshot_offsets("deep") == RUNTIME_SCREENSHOT_OFFSETS
    assert len(FAST_RUNTIME_SCREENSHOT_OFFSETS) <= 2


def test_attach_metadata_marks_runtime_attempted():
    snap = attach_grading_mode_metadata(
        {
            "artifact_inventory": {
                "runtime_observation_report": {
                    "status": "completed",
                    "runtime_depth": "fast",
                }
            }
        },
        "standard",
    )
    assert snap["grading_profile"]["runtime_attempted"] is True
    assert snap["grading_profile"]["runtime_depth"] == "fast"


def test_submission_processing_context():
    ctx = SubmissionProcessingContext.from_wire("pro")
    assert ctx.grading_mode is GradingMode.PRO
    assert ctx.wire_mode == "deep"
    assert ctx.profile.runtime_depth == "deep"
    assert ctx.flags["skip_runtime_observation"] is False


def test_attach_grading_mode_metadata():
    snap = attach_grading_mode_metadata({"grade_level": "U"}, "standard")
    assert snap["grading_mode"] == "fast"
    assert snap["grading_mode_label"] == "STANDARD"
    gp = snap["grading_profile"]
    assert gp["mode"] == "standard"
    assert gp["governance_shared"] is True
    assert gp["profile_version"]


def test_runtime_gate_invariant_across_modes():
    """Governance: same inventory → same gate block regardless of grading mode."""
    inventory = {
        "has_executable_artifacts": True,
        "runtime_artifacts": {"godot_export_detected": True},
        "runtime_observation_report": {"runtime_verified": False},
    }
    base = {
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": True, "awardable": True},
            {"criteria_level": "8/C.P6", "achieved": True, "awardable": True},
        ],
        "submission_paths": ["project.godot", "game.exe"],
    }
    for mode in ("fast", "deep"):
        snap = {**base, "grading_mode": mode, "artifact_inventory": inventory}
        apply_runtime_evidence_gate(snap)
        p5 = next(r for r in snap["criteria_results"] if "P5" in r["criteria_level"])
        assert p5.get("achieved") is False
        assert p5.get("runtime_gate_block") is True
