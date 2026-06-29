"""Academic Timeline Replay — event-sourced replay tests."""
from __future__ import annotations

from app.academic_event_replay import (
    append_academic_event,
    build_academic_timeline_replay,
    reconstruct_events_from_snapshot,
    seed_academic_event_log,
)
from app.explainability_migration import apply_explainability_backfill


def _snap() -> dict:
    return {
        "grade_level": "U",
        "total_score": 0,
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
            {"criteria_level": "8/C.P6", "achieved": False, "score": 0},
        ],
        "artifact_inventory": {
            "executable_artifacts": {"files": [{"name": "game.exe"}]},
            "runtime_observation_report": {
                "status": "gated",
                "reason": "GOVERNANCE_FREEZE_v1_active",
            },
        },
    }


def test_reconstruct_timeline_has_core_events():
    events = reconstruct_events_from_snapshot(_snap(), graded_at="2026-05-20T10:00:00Z")
    types = {e["event_type"] for e in events}
    assert "initial_grading" in types
    assert "runtime_gated" in types
    assert "criterion_decision" in types
    assert all(e.get("event_hash") for e in events)


def test_event_chain_links():
    snap = _snap()
    seed_academic_event_log(snap, graded_at="2026-05-20T10:00:00Z")
    events = snap["academic_event_log"]["events"]
    for i, ev in enumerate(events, start=1):
        assert ev.get("event_seq") == i
    for i in range(1, len(events)):
        assert events[i]["previous_event_hash"] == events[i - 1]["event_hash"]
    assert snap["academic_event_log"]["next_event_seq"] == len(events) + 1


def test_timeline_replay_by_date():
    replay = build_academic_timeline_replay(_snap(), graded_at="2026-05-20T10:00:00Z")
    assert replay["event_count"] >= 3
    assert replay["timeline_by_date"]
    assert replay["timeline_by_date"][0]["date"] == "2026-05-20"


def test_append_only_event_log():
    snap = _snap()
    seed_academic_event_log(snap)
    n0 = len(snap["academic_event_log"]["events"])
    from app.academic_event_replay import create_academic_event

    ev = create_academic_event(
        "governance_state",
        "SYSTEM",
        title_ar="test",
        detail_ar="test event",
    )
    append_academic_event(snap, ev)
    assert len(snap["academic_event_log"]["events"]) == n0 + 1


def test_backfill_includes_lineage_in_timeline():
    snap, _ = apply_explainability_backfill(_snap())
    seed_academic_event_log(snap, graded_at="2026-05-22T10:00:00Z")
    replay = build_academic_timeline_replay(snap)
    types = [e["event_type"] for e in replay["events"]]
    assert "explainability_revision" in types
    assert "evidence_lineage_attached" in types
