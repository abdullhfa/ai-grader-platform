"""Deterministic replay engine tests."""
from __future__ import annotations

from app.academic_event_replay import (
    create_academic_event,
    reconstruct_events_from_snapshot,
    seed_academic_event_log,
)
from app.deterministic_replay_engine import (
    EPOCH_POST_PLAYTEST_L5,
    EPOCH_RUNTIME_GATED,
    apply_event,
    compute_replayed_protected_digest,
    initial_replay_state,
    replay_events,
    verify_deterministic_replay,
)
from app.explainability_migration import _protected_digest, apply_explainability_backfill


def _full_snap() -> dict:
    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "U",
            "total_score": 0,
            "max_score": 100,
            "percentage": 0.0,
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
    )
    seed_academic_event_log(snap, graded_at="2026-05-20T10:00:00Z")
    return snap


def test_replay_is_pure_function():
    events = reconstruct_events_from_snapshot(_full_snap(), graded_at="2026-05-20T10:00:00Z")
    s1 = replay_events(events)
    s2 = replay_events(events)
    assert s1 == s2


def test_runtime_gated_epoch():
    events = reconstruct_events_from_snapshot(_full_snap(), graded_at="2026-05-20T10:00:00Z")
    state = replay_events(events)
    assert state["governance"]["runtime_gated"] is True
    assert state["replay_epoch"] in (
        EPOCH_RUNTIME_GATED,
        "POST_EXPLAINABILITY",
    )


def test_protected_digest_verification():
    snap = _full_snap()
    events = snap["academic_event_log"]["events"]
    v = verify_deterministic_replay(events, snap)
    assert v["reconstructed_protected_digest"]
    assert v["persisted_protected_digest"]
    assert v["protected_digest_match"] is True
    assert v["match"] is True


def test_playtest_epoch_transition():
    state = initial_replay_state()
    state = apply_event(
        state,
        create_academic_event(
            "human_playtest_completed",
            "HUMAN_PLAYTEST_L5",
            event_seq=1,
            payload={"pass": True},
        ),
    )
    assert state["replay_epoch"] == EPOCH_POST_PLAYTEST_L5
    assert state["playtest"]["completed"] is True


def test_authority_transition_mutates_criterion():
    state = initial_replay_state()
    state = apply_event(
        state,
        create_academic_event(
            "authority_transition",
            "HUMAN_PLAYTEST_L5",
            event_seq=2,
            payload={
                "criteria_level": "8/C.P5",
                "achieved_before": False,
                "achieved_after": True,
                "authority_from": "SYSTEM_GOVERNED",
                "authority_to": "HUMAN_PLAYTEST_L5",
            },
        ),
    )
    assert state["criteria"]["P5"]["achieved"] is True
    assert compute_replayed_protected_digest(state)
