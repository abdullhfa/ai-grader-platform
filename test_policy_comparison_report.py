"""Policy comparison batch report tests."""
from __future__ import annotations

from app.policy_comparison_report import build_batch_policy_comparison_report


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


def _snap_json() -> str:
    import json

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
                "executable_artifacts": {"files": [{"name": "g.exe"}]},
                "runtime_observation_report": {"status": "gated", "reason": "GOVERNANCE_FREEZE_v1_active"},
            },
        }
    )
    seed_academic_event_log(snap)
    return json.dumps(snap, ensure_ascii=False)


def test_batch_policy_comparison_report():
    db = _FakeDb([_FakeSub(1, _snap_json()), _FakeSub(2, _snap_json())])
    report = build_batch_policy_comparison_report(db, batch_id=99)
    assert report["counterfactual"] is True
    assert report["submissions_analyzed"] == 2
    assert "impact_analysis" in report
    assert "hold_reduction_rate" in report["impact_analysis"]
    assert report.get("report_hash")
    assert "normative_boundary_ar" in report
    assert report["drift_provenance_aggregate"] is not None
