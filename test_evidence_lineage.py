"""Evidence lineage DAG tests — C.P5/C.P6 decision provenance."""
from __future__ import annotations

from app.evidence_lineage import (
    attach_evidence_lineage_to_snapshot,
    build_evidence_lineage,
)
from app.explainability_migration import (
    apply_explainability_backfill,
    build_explainability_revision_meta,
    compute_revision_snapshot_hash,
)


def _abdullah_like_snapshot() -> dict:
    return {
        "grade_level": "U",
        "total_score": 0,
        "max_score": 100,
        "percentage": 0.0,
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
            {"criteria_level": "8/C.P6", "achieved": False, "score": 0},
        ],
        "artifact_inventory": {
            "executable_artifacts": {
                "files": [{"name": "My project (3).exe", "path": "/tmp/game.exe"}],
                "runtime_verified": False,
            },
            "documentation": {"status": "not_detected", "files": []},
            "source_code": {"status": "not_detected", "files": []},
            "testing_evidence": {"status": "not_detected"},
            "runtime_observation_report": {
                "status": "gated",
                "reason": "GOVERNANCE_FREEZE_v1_active",
            },
            "extraction_coverage": {
                "coverage_ratio": 0.027,
                "weak_analysis_risk": True,
            },
        },
    }


def test_lineage_detects_analyzed_source_code():
    snap = _abdullah_like_snapshot()
    snap["artifact_inventory"]["source_code"] = {
        "status": "analyzed",
        "files": [{"name": "player.gd"}, {"name": "main.gd"}],
    }
    attach_evidence_lineage_to_snapshot(snap)
    shared = snap["evidence_lineage"]["shared_nodes"]
    assert "evidence:code_extraction" in shared
    assert "evidence:code_missing" not in shared
    assert "استخراج كود" in shared["evidence:code_extraction"]["label_ar"]


def test_lineage_cp5_hold_with_governance_gate():
    snap = _abdullah_like_snapshot()
    attach_evidence_lineage_to_snapshot(snap)
    lineage = snap["evidence_lineage"]
    cp5 = lineage["criteria"]["C.P5"]
    assert cp5["status"] == "HOLD"
    assert cp5["decision_authority"] == "SYSTEM_GOVERNED"
    assert "governance:runtime_gate" in cp5["lineage"]["governance_nodes"]
    assert "evidence:runtime_not_verified" in cp5["lineage"]["evidence_nodes"]
    assert lineage.get("lineage_hash")


def test_shared_nodes_dag_reuse():
    snap = _abdullah_like_snapshot()
    attach_evidence_lineage_to_snapshot(snap)
    shared = snap["evidence_lineage"]["shared_nodes"]
    cp5_gov = snap["evidence_lineage"]["criteria"]["C.P5"]["lineage"]["governance_nodes"]
    cp6_gov = snap["evidence_lineage"]["criteria"]["C.P6"]["lineage"]["governance_nodes"]
    assert cp5_gov == cp6_gov
    assert cp5_gov[0] in shared


def test_lineage_included_in_snapshot_hash():
    snap = _abdullah_like_snapshot()
    updated, _ = apply_explainability_backfill(snap)
    layer = updated["explainability_layer"]
    assert layer.get("evidence_lineage")
    digest = updated["explainability_revision"]["protected_digest"]
    h1 = compute_revision_snapshot_hash(
        build_explainability_revision_meta(protected_digest=digest),
        layer,
        digest,
    )
    layer_copy = dict(layer)
    layer_copy["evidence_lineage"] = dict(layer["evidence_lineage"])
    layer_copy["evidence_lineage"]["criteria"]["C.P5"]["status"] = "ACHIEVED"
    h2 = compute_revision_snapshot_hash(
        build_explainability_revision_meta(protected_digest=digest),
        layer_copy,
        digest,
    )
    assert h1 != h2


def test_confidence_normalization():
    lineage = build_evidence_lineage(
        criteria_results=_abdullah_like_snapshot()["criteria_results"],
        inventory=_abdullah_like_snapshot()["artifact_inventory"],
    )
    assert lineage["confidence_model"] == "EVIDENCE_CONFIDENCE_v1"
    playtest = lineage["shared_nodes"].get("evidence:human_playtest")
    if playtest:
        assert playtest["confidence"] == 0.95
