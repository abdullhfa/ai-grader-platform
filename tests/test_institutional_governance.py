"""Phase 5 Sprint 2 — institutional governance layer tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def replay_snapshot(tmp_path, monkeypatch):
    """Minimal replay snapshot for governance tests."""
    submission_key = "student_a"
    session_id = "sess_001"
    base = tmp_path / "uploads" / "replay_snapshots" / submission_key / session_id
    (base / "runtime").mkdir(parents=True)
    (base / "evidence").mkdir(parents=True)
    (base / "ai_reasoning").mkdir(parents=True)
    (base / "grading_summary").mkdir(parents=True)
    (base / "screenshots").mkdir(parents=True)

    (base / "runtime" / "runtime.json").write_text(
        json.dumps({"status": "completed", "engine": "unity"}), encoding="utf-8"
    )
    (base / "evidence" / "evidence.json").write_text(
        json.dumps([{"criterion_id": "C.P5", "nodes": [{"node_id": "n1", "claim": "win", "confidence": 0.9}]}]),
        encoding="utf-8",
    )
    (base / "ai_reasoning" / "ai_reasoning.json").write_text(
        json.dumps({
            "final_decision": {
                "decision": "manual_review",
                "confidence": 0.42,
                "requires_manual_review": True,
                "reasoning_rejected": False,
            },
            "hallucination_flags": [],
            "agent_opinions": [{"contradictions": [{"type": "runtime_vs_gameplay"}]}],
        }),
        encoding="utf-8",
    )
    (base / "grading_summary" / "grading_summary.json").write_text(
        json.dumps({"grade_level": "MERIT", "percentage": 72}), encoding="utf-8"
    )
    (base / "deterministic_hash.json").write_text(
        json.dumps({"deterministic_hash": "abc123deadbeef", "session_id": session_id}),
        encoding="utf-8",
    )
    (base / "screenshots" / "frame_001.png").write_bytes(b"\x89PNG\r\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AI_GRADER_UPLOAD_ROOT", str(tmp_path / "uploads"))
    return submission_key, session_id


def test_replay_inspection_bundle(replay_snapshot):
    from app.governance.replay_viewer import load_replay_inspection_bundle

    key, sid = replay_snapshot
    bundle = load_replay_inspection_bundle(key, sid)
    assert bundle.deterministic_hash == "abc123deadbeef"
    assert bundle.runtime.get("engine") == "unity"
    assert len(bundle.screenshots) == 1
    assert bundle.bundle_complete is True
    assert bundle.contradictions


def test_policy_engine_mandatory_review(replay_snapshot):
    from app.governance.policy_engine import evaluate_policies
    from app.governance.replay_viewer import load_replay_inspection_bundle

    key, sid = replay_snapshot
    bundle = load_replay_inspection_bundle(key, sid)
    result = evaluate_policies(bundle)
    assert result["mandatory_manual_review"] is True


def test_examiner_review_replay_first(replay_snapshot):
    from app.governance.examiner_mode import load_examiner_review

    key, sid = replay_snapshot
    review = load_examiner_review(f"{key}/{sid}")
    assert review["examiner_guidance"]["mode"] == "replay_first"
    assert review["evidence_browser"]["total_nodes"] >= 1
    assert review["policy_evaluation"]["mandatory_manual_review"] is True


def test_override_and_audit_immutable(replay_snapshot):
    from app.governance.audit_log import read_audit_log
    from app.governance.override_engine import apply_grade_override
    from app.governance.permissions import GovernanceRole
    from app.governance.review_session import get_or_create_review_session

    key, sid = replay_snapshot
    session = get_or_create_review_session(key, sid, replay_hash="abc123deadbeef")
    result = apply_grade_override(
        session,
        actor="examiner@school.local",
        actor_role=GovernanceRole.EXAMINER,
        previous_grade="PASS",
        new_grade="MERIT",
        reason="runtime evidence insufficient",
        replay_hash="abc123deadbeef",
    )
    assert result["status"] == "ok"
    events = read_audit_log(sid)
    assert len(events) == 1
    assert events[0]["action"] == "override_grade"
    assert events[0]["previous"] == "PASS"
    assert events[0]["new"] == "MERIT"


def test_signoff_hash_linked_to_replay(replay_snapshot):
    from app.governance.permissions import GovernanceRole
    from app.governance.review_session import get_or_create_review_session
    from app.governance.signoff import apply_signoff, compute_signed_evaluation_hash

    key, sid = replay_snapshot
    session = get_or_create_review_session(key, sid, replay_hash="abc123deadbeef")
    out = apply_signoff(
        session,
        actor="senior@school.local",
        actor_role=GovernanceRole.SENIOR_EXAMINER,
        final_grade="MERIT",
        replay_hash="abc123deadbeef",
    )
    signed = out["signoff"]["signed_evaluation_hash"]
    assert len(signed) == 64
    assert out["signoff"]["replay_hash"] == "abc123deadbeef"

    h2 = compute_signed_evaluation_hash(
        replay_hash="abc123deadbeef",
        examiner_id="senior@school.local",
        timestamp=out["signoff"]["timestamp"],
        submission_key=key,
        session_id=sid,
        final_grade="MERIT",
    )
    assert h2 == signed


def test_appeal_requires_replay_snapshot(replay_snapshot):
    from app.appeals.appeal_engine import submit_appeal

    key, sid = replay_snapshot
    result = submit_appeal(
        submission_key=key,
        session_id=sid,
        student_id="student_a",
        reason="disagree with gameplay evidence interpretation",
    )
    assert result["status"] == "submitted"
    assert result["replay_anchor"] == "abc123deadbeef"
    assert result["policy"] == "replay_snapshot_only"


def test_appeal_rejected_without_snapshot(tmp_path, monkeypatch):
    from app.appeals.appeal_engine import submit_appeal

    monkeypatch.chdir(tmp_path)
    result = submit_appeal(
        submission_key="missing",
        session_id="none",
        student_id="student_x",
        reason="test",
    )
    assert result["status"] == "rejected"
    assert result["error"] == "replay_snapshot_required"


def test_permissions_matrix():
    from app.governance.permissions import GovernanceRole, has_permission

    assert has_permission(GovernanceRole.STUDENT, "submit_appeal")
    assert not has_permission(GovernanceRole.STUDENT, "override_grade")
    assert has_permission(GovernanceRole.EXAMINER, "override_grade")
    assert has_permission(GovernanceRole.SENIOR_EXAMINER, "final_signoff")
    assert has_permission(GovernanceRole.ADMIN, "audit_export")


def test_governance_isolation_layers():
    """Governance modules must not import runtime execution engines."""
    import app.governance.examiner_mode as em
    import app.appeals.appeal_engine as ae

    src_em = Path(em.__file__).read_text(encoding="utf-8")
    src_ae = Path(ae.__file__).read_text(encoding="utf-8")
    assert "runtime_engines" not in src_em
    assert "batch_grader" not in src_ae
    assert "sandbox_engine" not in src_ae
