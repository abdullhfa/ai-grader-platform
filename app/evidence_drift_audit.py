"""
Evidence drift audit — detect CRITICAL_EVIDENCE_DRIFT when bundle stable but evidence changed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.evidence_fingerprint import classify_reproducibility_drift


def audit_evidence_reproducibility(
    *,
    student_name: str,
    bundle_hash: str,
    evidence_hash: str,
    previous: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Compare current audit anchor to a prior submission for the same student.

    Returns alert dict when same rule bundle but evidence hash drifted (class B).
    """
    if not previous or not bundle_hash or not evidence_hash:
        return None

    prev_bundle = str(previous.get("bundle_hash") or "")
    prev_evidence = str(previous.get("evidence_hash") or "")
    if not prev_evidence or prev_bundle != bundle_hash or prev_evidence == evidence_hash:
        return None

    drift_class = classify_reproducibility_drift(
        bundle_hash_a=prev_bundle,
        bundle_hash_b=bundle_hash,
        evidence_hash_a=prev_evidence,
        evidence_hash_b=evidence_hash,
    )

    return {
        "alert": "CRITICAL_EVIDENCE_DRIFT",
        "severity": "critical",
        "drift_class": drift_class,
        "student_name": student_name,
        "bundle_hash": bundle_hash,
        "previous_evidence_hash": prev_evidence,
        "current_evidence_hash": evidence_hash,
        "message_ar": (
            "تغيّرت بصمة الأدلة مع نفس قواعد التصحيح — راجع عزل الملفات أو Vision "
            "(Evidence Changed وليس Grade Changed فقط)."
        ),
    }


def prior_anchor_from_snapshot(snapshot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not snapshot:
        return None
    fp = snapshot.get("evidence_fingerprint") or {}
    prov = snapshot.get("decision_provenance") or {}
    if not fp.get("evidence_hash") or not prov.get("bundle_hash"):
        inv = snapshot.get("artifact_inventory") or {}
        fp = fp or inv.get("evidence_fingerprint") or {}
        prov = prov or inv.get("decision_provenance") or {}
    if not fp.get("evidence_hash"):
        return None
    return {
        "bundle_hash": prov.get("bundle_hash"),
        "evidence_hash": fp.get("evidence_hash"),
        "submission_id": snapshot.get("submission_id"),
    }


def attach_evidence_drift_audit(
    grading_result: Dict[str, Any],
    *,
    prior_anchor: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Attach drift audit block to grading_result when prior anchor exists."""
    fp = grading_result.get("evidence_fingerprint") or {}
    prov = grading_result.get("decision_provenance") or {}
    alert = audit_evidence_reproducibility(
        student_name=str(grading_result.get("student_name") or ""),
        bundle_hash=str(prov.get("bundle_hash") or ""),
        evidence_hash=str(fp.get("evidence_hash") or ""),
        previous=prior_anchor,
    )
    if alert:
        grading_result["evidence_drift_audit"] = alert
    return alert
