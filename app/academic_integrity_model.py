"""
Academic Integrity Model — unified hash terminology.

| Hash              | Protects                          |
| ----------------- | --------------------------------- |
| protected_digest  | Academic decision (grades/criteria)|
| snapshot_hash     | Explainability state at revision  |
| lineage_hash      | Evidence→governance→decision graph |
| event_hash        | Append-only event sequence chain  |
"""
from __future__ import annotations

from typing import Any, Dict

INTEGRITY_MODEL_VERSION = "1.0"

INTEGRITY_LAYERS: Dict[str, Dict[str, str]] = {
    "protected_digest": {
        "role": "decision_boundary",
        "protects_ar": "القرار الأكademي — الدرجة، المعايير، التحكيم",
        "protects_en": "Academic decision — grades, criteria, adjudication",
    },
    "snapshot_hash": {
        "role": "state_anchor",
        "protects_ar": "حالة explainability + lineage عند revision",
        "protects_en": "Explainability + lineage state at revision",
    },
    "lineage_hash": {
        "role": "interpretation_anchor",
        "protects_ar": "DAG التفسير — evidence → governance → decision",
        "protects_en": "Interpretation DAG — evidence → governance → decision",
    },
    "event_hash": {
        "role": "sequence_anchor",
        "protects_ar": "تسلسل الأحداث append-only",
        "protects_en": "Append-only event sequence integrity",
    },
}


def build_integrity_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only integrity anchors present on a grading snapshot."""
    rev = snapshot.get("explainability_revision") or {}
    layer = snapshot.get("explainability_layer") or {}
    lineage = layer.get("evidence_lineage") or snapshot.get("evidence_lineage") or {}
    log = snapshot.get("academic_event_log") or {}

    from app.explainability_migration import _protected_digest

    digest = None
    try:
        digest = _protected_digest(snapshot)
    except Exception:
        pass

    return {
        "model_version": INTEGRITY_MODEL_VERSION,
        "layers": INTEGRITY_LAYERS,
        "anchors": {
            "protected_digest": digest,
            "snapshot_hash": rev.get("snapshot_hash"),
            "lineage_hash": lineage.get("lineage_hash"),
            "event_chain_head": log.get("chain_head_hash"),
            "next_event_seq": log.get("next_event_seq"),
        },
    }
