"""Replay-based Disparity Analytics tests."""
from __future__ import annotations

import json

from app.replay_disparity_analytics import (
    analyze_submission_replay_disparity,
    build_batch_replay_disparity_report,
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
                "testing_evidence": {"files": [{"name": "test.png"}]},
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


def test_analyze_submission_replay_disparity():
    sub = _FakeSub(1, _runtime_snap())
    row = analyze_submission_replay_disparity(sub)
    assert row["skipped"] is False
    assert "runtime_only" in row["replay_cohorts"]
    assert row["replay_outcome"]["hold_present"] is True
    assert row["drift_sensitivity"]["counterfactual"] is True
    assert row["comparability_key"]


def test_batch_replay_disparity_report():
    db = _FakeDb([_FakeSub(1, _runtime_snap()), _FakeSub(2, _word_snap())])
    report = build_batch_replay_disparity_report(db, batch_id=99)
    assert report["read_only"] is True
    assert report["disparity_contract"] == "replay_disparity_v1"
    assert report["comparison_basis"] == "same_epoch_same_contract"
    assert report["disparity_contract_spec"]["reducer_version"] == "1.0"
    assert report["replay_cohort_registry"]["definition_contract"] == "cohort_v1"
    assert report["epistemic_comparability_guard"]["cross_contract_disparity_allowed"] is False
    assert report["submissions_analyzed"] == 2
    assert len(report["outcome_divergence"]) >= 2
    assert "authority_dependency_disparity" in report
    assert "replay_stability_disparity" in report
    assert "drift_sensitivity_disparity" in report
    assert "disparity_concentration_zones" in report
    assert report.get("report_hash")
    serialized = json.dumps(report, ensure_ascii=False).lower()
    assert '"bias"' not in serialized
    assert '"discrimination"' not in serialized
    assert '"unfair"' not in serialized
