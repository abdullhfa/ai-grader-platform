"""Evidence Fingerprint v1 — reproducibility with rule bundle."""
from __future__ import annotations

import hashlib
from typing import Any

from app.evidence_fingerprint import (
    FINGERPRINT_VERSION,
    attach_evidence_fingerprint,
    build_evidence_fingerprint,
    classify_reproducibility_drift,
    compute_evidence_hash,
)
from app.explainability_migration import compute_academic_decision_digest
from app.rule_bundle import build_decision_provenance


def test_evidence_hash_changes_when_word_changes():
    h1 = compute_evidence_hash(
        word_hash="aaa",
        source_code_hash="b" * 64,
        visual_hash="c" * 64,
        video_hash="d" * 64,
    )
    h2 = compute_evidence_hash(
        word_hash="bbb",
        source_code_hash="b" * 64,
        visual_hash="c" * 64,
        video_hash="d" * 64,
    )
    assert h1 != h2


def test_visual_hash_uses_analyzed_batches_only():
    fp = build_evidence_fingerprint(
        content_fingerprint={"content_hash": hashlib.sha256(b"doc").hexdigest()},
        visual_evidence_summary={
            "images_found": 20,
            "images_used_in_decision": 10,
            "images_analyzed": 10,
            "vision_completed": True,
            "vision_batches": [
                {"lane": "docx_embedded", "submitted": 10, "analyzed": 10},
                {"lane": "video_keyframe", "submitted": 5, "analyzed": 0, "error": "fail"},
            ],
        },
    )
    assert fp["visual_hash"] != "0" * 64
    assert fp["evidence_hash"]


def test_source_code_hash_from_inventory_files():
    fp = build_evidence_fingerprint(
        content_fingerprint={"content_hash": "w" * 64},
        artifact_inventory={
            "source_code": {
                "files": [
                    {"name": "main.gd", "ext": ".gd", "size_bytes": 1200},
                    {"name": "player.gd", "ext": ".gd", "size_bytes": 800},
                ]
            }
        },
    )
    assert fp["source_code_hash"] != "0" * 64


def test_classify_drift_matrix():
    assert classify_reproducibility_drift(
        bundle_hash_a="b1", bundle_hash_b="b1", evidence_hash_a="e1", evidence_hash_b="e1"
    ) == "A_rules_and_evidence_stable"
    assert classify_reproducibility_drift(
        bundle_hash_a="b1", bundle_hash_b="b1", evidence_hash_a="e1", evidence_hash_b="e2"
    ) == "B_evidence_changed"
    assert classify_reproducibility_drift(
        bundle_hash_a="b1", bundle_hash_b="b2", evidence_hash_a="e1", evidence_hash_b="e1"
    ) == "C_rules_changed"


def test_attach_copies_to_inventory_and_provenance():
    grading: dict[str, Any] = {
        "grading_mode": "fast",
        "content_fingerprint": {"content_hash": hashlib.sha256(b"x").hexdigest()},
        "visual_evidence_summary": {
            "images_used_in_decision": 5,
            "images_analyzed": 5,
            "vision_completed": True,
            "vision_batches": [{"lane": "docx_embedded", "submitted": 5, "analyzed": 5}],
        },
        "decision_provenance": build_decision_provenance("fast"),
        "artifact_inventory": {"source_code": {"files": [{"name": "a.gd", "ext": ".gd", "size_bytes": 1}]}},
    }
    attach_evidence_fingerprint(grading)
    fp_raw = grading["evidence_fingerprint"]
    assert isinstance(fp_raw, dict)
    fp: dict[str, Any] = fp_raw
    inv_fp = grading["artifact_inventory"]["evidence_fingerprint"]
    assert isinstance(inv_fp, dict)
    prov = grading["decision_provenance"]
    assert isinstance(prov, dict)
    assert fp["version"] == FINGERPRINT_VERSION
    assert inv_fp["evidence_hash"] == fp["evidence_hash"]
    assert prov["evidence_hash"] == fp["evidence_hash"]


def test_academic_digest_includes_evidence_fingerprint():
    prov = build_decision_provenance("fast")
    fp = build_evidence_fingerprint(content_fingerprint={"content_hash": "w" * 64})
    d1 = compute_academic_decision_digest(
        grade_level="U",
        percentage=62.0,
        criteria_results=[{"criteria_level": "8/C.P6", "achieved": False}],
        decision_provenance=prov,
        evidence_fingerprint=fp,
    )
    d2 = compute_academic_decision_digest(
        grade_level="U",
        percentage=62.0,
        criteria_results=[{"criteria_level": "8/C.P6", "achieved": False}],
        decision_provenance=prov,
        evidence_fingerprint=build_evidence_fingerprint(
            content_fingerprint={"content_hash": "z" * 64}
        ),
    )
    assert d1 != d2
