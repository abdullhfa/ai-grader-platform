"""Evidence Fairness Analytics tests."""
from __future__ import annotations

import json

from app.evidence_fairness_analytics import (
    build_batch_evidence_fairness_report,
    classify_evidence_profiles,
    analyze_submission_evidence_fairness,
)


class _FakeSummary:
    graded_at = None


class _FakeSub:
    def __init__(self, sid: int, snap_json: str, name: str = ""):
        self.id = sid
        self.student_name = name or f"Student {sid}"
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


def test_classify_runtime_only():
    snap = json.loads(_runtime_snap())
    profiles = classify_evidence_profiles(snap)
    assert "runtime_only" in profiles


def test_classify_word_pdf():
    snap = json.loads(_word_snap())
    profiles = classify_evidence_profiles(snap)
    assert "word_pdf" in profiles
    assert "documentation_rich" in profiles


def test_analyze_submission_row():
    sub = _FakeSub(1, _runtime_snap())
    row = analyze_submission_evidence_fairness(sub)
    assert row["skipped"] is False
    assert row["hold_present"] is True
    assert "runtime_only" in row["evidence_profiles"]


def test_batch_evidence_fairness_report():
    db = _FakeDb(
        [
            _FakeSub(1, _runtime_snap()),
            _FakeSub(2, _word_snap()),
        ]
    )
    report = build_batch_evidence_fairness_report(db, batch_id=42)
    assert report["read_only"] is True
    assert report["fairness_epoch"] == "EVIDENCE_FAIRNESS_v1"
    assert report["metric_contract"] == "evidence_distribution_v1"
    assert report["submissions_analyzed"] == 2
    assert len(report["evidence_fairness_matrix"]) >= 2
    assert report.get("report_hash")
    assert "normative_boundary_ar" in report
    serialized = json.dumps(report, ensure_ascii=False)
    assert '"unfair"' not in serialized.lower()
    assert "unfairness_verdict" not in serialized.lower()
    matrix_profiles = {r["profile"] for r in report["evidence_fairness_matrix"]}
    assert "runtime_only" in matrix_profiles
    assert "word_pdf" in matrix_profiles
