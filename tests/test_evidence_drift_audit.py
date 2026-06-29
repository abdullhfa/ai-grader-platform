"""Evidence drift audit alerts."""
from __future__ import annotations

from app.evidence_drift_audit import audit_evidence_reproducibility


def test_critical_drift_same_bundle_different_evidence():
    alert = audit_evidence_reproducibility(
        student_name="Test",
        bundle_hash="bundle123",
        evidence_hash="evidence_new",
        previous={"bundle_hash": "bundle123", "evidence_hash": "evidence_old"},
    )
    assert alert is not None
    assert alert["alert"] == "CRITICAL_EVIDENCE_DRIFT"
    assert alert["drift_class"] == "B_evidence_changed"


def test_no_alert_when_both_stable():
    assert (
        audit_evidence_reproducibility(
            student_name="Test",
            bundle_hash="b1",
            evidence_hash="e1",
            previous={"bundle_hash": "b1", "evidence_hash": "e1"},
        )
        is None
    )
