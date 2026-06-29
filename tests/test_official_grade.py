"""Tests for resolve_official_grade — Phase 1 single source of truth."""
from __future__ import annotations

from app.official_grade import resolve_official_grade


def _game_snapshot(*, achieved_p5: bool = True, runtime_satisfied: bool = False) -> dict:
    inv = {
        "runtime_artifacts": {"scratch_detected": True},
        "has_executable_artifacts": True,
    }
    if runtime_satisfied:
        inv["runtime_observation_report"] = {
            "runtime_verified": True,
            "functional_smoke_pass": True,
            "launch_ok": True,
        }
        inv["l5_human_playtest"] = {"verified": True, "status": "complete_visual"}
    snap = {
        "grade_level": "P - Pass" if achieved_p5 else "U",
        "criteria_results": [
            {
                "criteria_level": "8/B.P3",
                "achieved": True,
                "awardable": True,
                "score": 100,
            },
            {
                "criteria_level": "8/B.P4",
                "achieved": True,
                "awardable": True,
                "score": 100,
            },
            {
                "criteria_level": "8/C.P5",
                "achieved": achieved_p5,
                "awardable": achieved_p5,
                "score": 100 if achieved_p5 else 0,
            },
            {
                "criteria_level": "8/C.P6",
                "achieved": achieved_p5,
                "awardable": achieved_p5,
                "score": 100 if achieved_p5 else 0,
            },
        ],
        "artifact_inventory": inv,
        "submission_paths": ["game/project.sb3"],
    }
    return snap


def test_legacy_db_fallback_when_no_snapshot():
    official = resolve_official_grade(None, legacy_grade_level="M - Merit")
    assert official.grade == "M"
    assert official.source == "legacy_db"
    assert official.is_stale is True


def test_old_snapshot_without_gate_key_gets_reapplied_to_u():
    """Pre-gate snapshot: AI gave P but no runtime → U after reapply."""
    snap = _game_snapshot(achieved_p5=True, runtime_satisfied=False)
    assert "runtime_evidence_gate" not in snap

    official = resolve_official_grade(snap, reapply_pipeline=True)

    assert official.grade == "U"
    assert "runtime_evidence_gate" in snap
    assert official.gate_applied is True
    assert official.gate_satisfied is False
    assert official.source == "pipeline"
    assert official.reapply_change_count >= 1


def test_word_only_snapshot_gate_skipped():
    snap = {
        "grade_level": "P - Pass",
        "criteria_results": [
            {"criteria_level": "8/B.P3", "achieved": True, "awardable": True, "score": 100},
        ],
        "artifact_inventory": {"documentation": {"status": "detected", "files": [{"ext": ".docx"}]}},
    }
    official = resolve_official_grade(snap, reapply_pipeline=True)
    gate = snap.get("runtime_evidence_gate") or {}
    assert gate.get("reason") == "not_a_game_submission"
    assert official.gate_satisfied is None
    assert official.grade == "P"


def test_reapply_false_reads_post_gate_snapshot():
    snap = _game_snapshot(achieved_p5=False, runtime_satisfied=False)
    snap["runtime_evidence_gate"] = {
        "applied": True,
        "satisfied": False,
        "version": "runtime_evidence_gate_v1",
    }
    snap["grade_level"] = "U - Unclassified"

    official = resolve_official_grade(snap, reapply_pipeline=False)
    assert official.grade == "U"
    assert official.reapply_change_count == 0


def test_downgrades_collected_from_gate():
    snap = _game_snapshot(achieved_p5=True, runtime_satisfied=False)
    official = resolve_official_grade(snap, reapply_pipeline=True)
    layers = {d.get("layer") for d in official.downgrades}
    assert "runtime_evidence_gate" in layers or "runtime_gate_block" in layers
