"""Procedural Fairness Analytics tests."""
from __future__ import annotations

import json

from app.procedural_fairness_analytics import (
    analyze_submission_procedural_fairness,
    build_batch_procedural_fairness_report,
    classify_procedural_archetype,
    extract_procedural_path,
)


class _FakeSummary:
    graded_at = None


class _FakeSub:
    def __init__(self, sid: int, snap_json: str):
        self.id = sid
        self.student_name = f"Student {sid}"
        self.summary = _FakeSummary()
        self.grading_snapshot_json = snap_json


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, subs):
        self._subs = subs

    def query(self, model):
        return _FakeQuery(self._subs)


def _runtime_snap() -> str:
    from app.academic_event_replay import seed_academic_event_log
    from app.explainability_migration import apply_explainability_backfill

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
                "executable_artifacts": {"files": [{"name": "game.exe"}]},
                "runtime_observation_report": {
                    "status": "gated",
                    "reason": "GOVERNANCE_FREEZE_v1_active",
                },
            },
        }
    )
    seed_academic_event_log(snap)
    return json.dumps(snap, ensure_ascii=False)


def _word_snap() -> str:
    from app.academic_event_replay import seed_academic_event_log
    from app.explainability_migration import apply_explainability_backfill

    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "P",
            "total_score": 50,
            "max_score": 100,
            "percentage": 50.0,
            "criteria_results": [
                {"criteria_level": "8/C.P5", "achieved": True, "score": 8},
            ],
            "artifact_inventory": {
                "documentation": {
                    "files": [{"name": "report.docx", "ext": ".docx"}],
                    "status": "analyzed",
                },
                "source_code": {"files": [{"name": "Main.cs"}]},
                "extraction_coverage": {
                    "coverage_ratio": 0.85,
                    "weak_analysis_risk": False,
                },
            },
        }
    )
    seed_academic_event_log(snap)
    return json.dumps(snap, ensure_ascii=False)


def test_runtime_procedural_path():
    from app.academic_event_replay import build_academic_timeline_replay
    from app.authority_transition_replay import build_authority_transition_replay
    from app.deterministic_replay_engine import verify_deterministic_replay

    snap = json.loads(_runtime_snap())
    timeline = build_academic_timeline_replay(snap)
    events = timeline["events"]
    verification = verify_deterministic_replay(events, snap)
    authority = build_authority_transition_replay(snap, events=events)
    path = extract_procedural_path(
        events,
        timeline_source=timeline["source"],
        snap=snap,
        replay_state=verification.get("state_summary") or {},
        authority_report=authority,
        verification=verification,
    )
    assert path["runtime_gated"] is True
    assert path["hold_present"] is True
    assert path["human_escalated"] is True


def test_archetype_governance_gated():
    path = {
        "replay_unstable": False,
        "governance_gate_persistent": True,
        "hold_present": True,
        "human_escalated": True,
        "runtime_gated": True,
    }
    assert classify_procedural_archetype(path, ["word_pdf"]) == "governance_gated"


def test_analyze_submission_procedural():
    sub = _FakeSub(1, _runtime_snap())
    row = analyze_submission_procedural_fairness(sub)
    assert row["skipped"] is False
    assert row["procedural_archetype"] in (
        "governance_gated",
        "evidence_sparse",
        "replay_unstable",
    )
    assert row["procedural_path"]["timeline_source"] == "persisted_event_log"


def test_batch_procedural_fairness_report():
    db = _FakeDb([_FakeSub(1, _runtime_snap()), _FakeSub(2, _word_snap())])
    report = build_batch_procedural_fairness_report(db, batch_id=7)
    assert report["read_only"] is True
    assert report["procedural_epoch"] == "PROCEDURAL_ANALYTICS_v1"
    assert report["submissions_analyzed"] == 2
    assert report.get("report_hash")
    assert len(report["procedural_flow_by_profile"]) >= 2
    assert "procedural_bottlenecks" in report
    assert "authority_transition_latency_histogram" in report
    serialized = json.dumps(report, ensure_ascii=False).lower()
    assert '"bias"' not in serialized
    assert '"discrimination"' not in serialized
    assert '"unfair"' not in serialized
