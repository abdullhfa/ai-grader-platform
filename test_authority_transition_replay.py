"""Authority transition replay — semantic diff tests."""
from __future__ import annotations

from app.academic_event_replay import seed_academic_event_log
from app.authority_transition_replay import build_authority_transition_replay
from app.explainability_migration import apply_explainability_backfill


def _snap_with_lineage() -> dict:
    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "U",
            "criteria_results": [
                {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
            ],
            "artifact_inventory": {
                "executable_artifacts": {"files": [{"name": "game.exe"}]},
                "runtime_observation_report": {
                    "status": "gated",
                    "reason": "GOVERNANCE_FREEZE_v1_active",
                },
            },
        }
    )
    seed_academic_event_log(snap, graded_at="2026-05-20T10:00:00Z")
    return snap


def test_governance_transition_in_replay():
    replay = build_authority_transition_replay(_snap_with_lineage())
    assert replay["transition_count"] >= 1
    gov = [t for t in replay["transitions"] if t["to_authority"] == "SYSTEM_GOVERNED"]
    assert gov
    assert gov[0]["reasons"]


def test_transition_has_impact_fields():
    snap = _snap_with_lineage()
    snap["runtime_adjudication_db_sync"] = {
        "applied": True,
        "row_changes": [
            {
                "criteria_level": "8/C.P5",
                "achieved_before": False,
                "achieved_after": True,
                "achievement_authority": "HUMAN_PLAYTEST_L5",
            }
        ],
    }
    seed_academic_event_log(snap, force=True)
    replay = build_authority_transition_replay(snap)
    tr = [t for t in replay["transitions"] if t.get("impact", {}).get("achieved_after") is True]
    assert tr
    assert tr[0]["impact"]["status_before"]
    assert tr[0]["impact"]["status_after"]
