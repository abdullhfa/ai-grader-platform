"""Governance analytics consumer tests."""
from __future__ import annotations

from app.deterministic_replay_engine import verify_deterministic_replay
from app.explainability_migration import apply_explainability_backfill
from app.governance_analytics import analyze_submission_governance


class _FakeSub:
    id = 1
    student_name = "Test"
    summary = None
    grading_snapshot_json = None


def _snap_json() -> str:
    import json

    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "U",
            "total_score": 0,
            "max_score": 100,
            "percentage": 0.0,
            "criteria_results": [
                {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
            ],
            "artifact_inventory": {
                "executable_artifacts": {"files": [{"name": "g.exe"}]},
                "runtime_observation_report": {
                    "status": "gated",
                    "reason": "GOVERNANCE_FREEZE_v1_active",
                },
            },
        }
    )
    from app.academic_event_replay import seed_academic_event_log

    seed_academic_event_log(snap)
    return json.dumps(snap, ensure_ascii=False)


def test_semantic_verification_fields():
    import json

    snap = json.loads(_snap_json())
    events = snap["academic_event_log"]["events"]
    v = verify_deterministic_replay(events, snap)
    assert "semantic_replay_verified" in v
    assert "authority_match" in v
    assert "lineage_match" in v
    assert "governance_match" in v
    assert v.get("epoch_metadata")


def test_analyze_submission_row():
    sub = _FakeSub()
    sub.grading_snapshot_json = _snap_json()
    row = analyze_submission_governance(sub)
    assert row["skipped"] is False
    assert row["runtime_gated"] is True
    assert "replay_epoch" in row
