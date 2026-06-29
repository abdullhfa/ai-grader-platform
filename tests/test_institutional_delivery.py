"""Phase 5 Sprint 3 — institutional delivery layer tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def replay_snapshot(tmp_path, monkeypatch):
    submission_key = "student_a"
    session_id = "sess_001"
    base = tmp_path / "uploads" / "replay_snapshots" / submission_key / session_id
    for sub in ("runtime", "evidence", "ai_reasoning", "grading_summary", "gameplay", "screenshots"):
        (base / sub).mkdir(parents=True)

    timeline = {
        "duration_seconds": 14.0,
        "events": [
            {"timestamp": 1.0, "type": "scene_loaded", "confidence": 0.95},
            {"timestamp": 5.0, "type": "movement_detected", "confidence": 0.88},
            {"timestamp": 8.0, "type": "freeze_detected", "confidence": 0.72},
            {"timestamp": 12.0, "type": "score_changed", "confidence": 0.81},
        ],
    }
    (base / "gameplay" / "gameplay.json").write_text(json.dumps(timeline), encoding="utf-8")
    (base / "runtime" / "runtime.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (base / "evidence" / "evidence.json").write_text(
        json.dumps([{"criterion_id": "C.P5", "nodes": [{"node_id": "n1", "claim": "win", "confidence": 0.9}]}]),
        encoding="utf-8",
    )
    (base / "ai_reasoning" / "ai_reasoning.json").write_text(
        json.dumps({"final_decision": {"decision": "manual_review", "confidence": 0.55}}),
        encoding="utf-8",
    )
    (base / "grading_summary" / "grading_summary.json").write_text(
        json.dumps({"grade_level": "MERIT"}), encoding="utf-8"
    )
    (base / "deterministic_hash.json").write_text(
        json.dumps({"deterministic_hash": "a" * 64}), encoding="utf-8"
    )
    (base / "screenshots" / "f.png").write_bytes(b"\x89PNG\r\n")

    monkeypatch.chdir(tmp_path)
    return submission_key, session_id


def test_timeline_presenter_format(replay_snapshot):
    from app.governance.replay_viewer import load_replay_inspection_bundle
    from app.governance_ui.presenters.timeline_presenter import present_timeline

    key, sid = replay_snapshot
    bundle = load_replay_inspection_bundle(key, sid)
    vm = present_timeline(bundle)
    assert vm["event_count"] == 4
    assert vm["events"][0]["time_label"] == "00:01"
    assert vm["events"][0]["confidence_class"] == "conf-high"
    assert "00:08 freeze_detected" in " ".join(vm["summary_lines"])


def test_evidence_graph_presenter(replay_snapshot):
    from app.governance.examiner_mode import load_examiner_review
    from app.governance_ui.presenters.replay_presenter import present_replay_investigation

    key, sid = replay_snapshot
    inv = present_replay_investigation(load_examiner_review(f"{key}/{sid}"))
    assert inv["evidence"]["total_nodes"] >= 1
    assert inv["evidence"]["criteria"][0]["criterion_id"] == "C.P5"
    assert inv["review_mode"] == "replay_first"


def test_signed_pdf_generation(replay_snapshot):
    from app.governance.signed_pdf_report import build_signed_pdf_report

    key, sid = replay_snapshot
    pdf = build_signed_pdf_report(key, sid)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500


def test_pdf_signature_consistency(replay_snapshot):
    from app.governance.institutional_export import export_signed_report_stub
    from app.governance.permissions import GovernanceRole
    from app.governance.review_session import get_or_create_review_session
    from app.governance.signoff import apply_signoff
    from app.governance.signed_pdf_report import build_signed_pdf_report

    key, sid = replay_snapshot
    replay_hash = "a" * 64
    session = get_or_create_review_session(key, sid, replay_hash=replay_hash)
    signoff = apply_signoff(
        session,
        actor="examiner@school.local",
        actor_role=GovernanceRole.SENIOR_EXAMINER,
        final_grade="DISTINCTION",
        replay_hash=replay_hash,
    )
    signed = signoff["signoff"]["signed_evaluation_hash"]
    stub = export_signed_report_stub(key, sid, signed_evaluation_hash=signed)
    assert stub["signed_evaluation_hash"] == signed
    assert stub["replay_hash"] == replay_hash

    pdf = build_signed_pdf_report(key, sid, signed_evaluation_hash=signed)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 800
    assert stub["replay_hash"] == replay_hash


def test_lms_csv_export(replay_snapshot):
    from app.governance.lms_export import export_lms_csv, export_lms_json

    key, sid = replay_snapshot
    records = [{"submission_key": key, "session_id": sid, "grade_level": "MERIT", "percentage": 72}]
    csv_out = export_lms_csv(records)
    assert "student_id" in csv_out
    assert key in csv_out

    json_out = export_lms_json(records)
    assert json_out["schema"] == "lms_grade_export_v1"
    assert json_out["records"][0]["submission_key"] == key


def test_schema_contracts_list():
    from app.governance.schema_contracts import list_contract_schemas

    names = list_contract_schemas()
    assert "replay.schema.json" in names
    assert "audit.schema.json" in names
    assert len(names) >= 6


def test_replay_schema_validation(replay_snapshot):
    from app.governance.replay_viewer import load_replay_inspection_bundle
    from app.governance.schema_contracts import validate_against_schema

    key, sid = replay_snapshot
    bundle = load_replay_inspection_bundle(key, sid).to_dict()
    ok, errors = validate_against_schema(bundle, "replay.schema.json")
    if errors == ["jsonschema not installed — validation skipped"]:
        pytest.skip("jsonschema optional")
    assert ok, errors


def test_e2e_governance_pipeline(replay_snapshot):
    """submission → replay → governance → appeal → signed report."""
    from app.appeals.appeal_engine import submit_appeal
    from app.governance.audit_log import read_audit_log
    from app.governance.examiner_mode import load_examiner_review
    from app.governance.override_engine import apply_grade_override
    from app.governance.permissions import GovernanceRole
    from app.governance.review_session import get_or_create_review_session
    from app.governance.signoff import apply_signoff
    from app.governance.signed_pdf_report import build_signed_pdf_report

    key, sid = replay_snapshot
    review = load_examiner_review(f"{key}/{sid}")
    assert review["replay_bundle"]["deterministic_hash"]

    session = get_or_create_review_session(key, sid, replay_hash="a" * 64)
    apply_grade_override(
        session,
        actor="examiner@school.local",
        actor_role=GovernanceRole.EXAMINER,
        previous_grade="MERIT",
        new_grade="DISTINCTION",
        reason="replay evidence supports upgrade",
        replay_hash="a" * 64,
    )
    session = get_or_create_review_session(key, sid)
    signoff = apply_signoff(
        session,
        actor="senior@school.local",
        actor_role=GovernanceRole.SENIOR_EXAMINER,
        final_grade="DISTINCTION",
        replay_hash="a" * 64,
    )

    appeal = submit_appeal(
        submission_key=key,
        session_id=sid,
        student_id=key,
        reason="disagree with freeze interpretation",
    )
    assert appeal["status"] == "submitted"

    assert len(read_audit_log(sid)) >= 2
    pdf = build_signed_pdf_report(key, sid)
    assert pdf.startswith(b"%PDF")
    assert signoff["signoff"]["signed_evaluation_hash"]


def test_corrupted_evidence_graph_resilience(replay_snapshot):
    from app.governance.replay_viewer import load_replay_inspection_bundle
    from app.governance_ui.presenters.evidence_presenter import present_evidence_graph

    key, sid = replay_snapshot
    bundle = load_replay_inspection_bundle(key, sid)
    bundle.evidence = "not-a-graph"
    vm = present_evidence_graph(bundle, None)
    assert vm["total_nodes"] == 0


def test_replay_rehydration_for_appeal(replay_snapshot):
    from app.appeals.evidence_rehydrator import rehydrate_appeal_evidence

    key, sid = replay_snapshot
    out = rehydrate_appeal_evidence(key, sid)
    assert out["status"] == "ok"
    assert out["rehydration_policy"] == "no_runtime_reexecution"
    assert out["deterministic_hash"] == "a" * 64
