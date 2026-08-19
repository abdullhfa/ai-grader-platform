from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.governance_decision import (
    AcademicOutcome,
    GovernanceDecisionSnapshot,
    RuntimeEvidenceIdentityMismatch,
    VerificationBlockerOrigin,
    VerificationOutcome,
    legacy_to_governance_snapshot,
    require_final_award,
    validate_runtime_evidence_identity,
)


def test_jana_resolver_selects_v2_inside_submission_root_with_arabic_paths(tmp_path: Path):
    root = tmp_path / "Jana Dwiri U8 L3"
    yyp = root / "Project" / "التطوير" / "code" / "M" / "CheeseChase.yyp"
    yyp.parent.mkdir(parents=True)
    yyp.write_text(json.dumps({"resourceType": "GMProject", "resources": []}), encoding="utf-8")
    (yyp.parent / "player.gml").write_text("x += 1", encoding="utf-8")
    for version in ("V1", "V2"):
        export = root / "Project" / "التطوير" / version
        export.mkdir(parents=True)
        (export / "CheeseChase.exe").write_bytes(b"MZ")
        (export / "data.win").write_bytes(b"win")
        (export / "options.ini").write_text("[Windows]", encoding="utf-8")
    # A similarly named executable in another extracted submission is not evidence.
    foreign = tmp_path / "web_static" / "CheeseChase.exe"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"MZ")

    from app.runtime_engines.gamemaker.project_probe import probe_gamemaker_layout
    layout = probe_gamemaker_layout(root)
    assert layout.yyp_path == yyp
    assert layout.executable == root / "Project" / "التطوير" / "V2" / "CheeseChase.exe"
    assert str(foreign) != str(layout.executable)


def test_pending_runtime_snapshot_never_turns_into_final_u():
    decision = GovernanceDecisionSnapshot(
        calculated_band="U",
        verification_blocker_origin=VerificationBlockerOrigin.SYSTEM,
        selected_version="V2",
    )
    assert decision.official_grade is None
    assert decision.academic_outcome == AcademicOutcome.PENDING
    assert decision.engine_id == "gamemaker"
    with pytest.raises(ValidationError):
        GovernanceDecisionSnapshot(official_grade="U")


def test_only_verified_requirement_failure_is_not_achieved():
    decision = GovernanceDecisionSnapshot(
        verification_outcome=VerificationOutcome.VERIFIED_REQUIREMENT_FAILED,
        verification_blocker_origin=VerificationBlockerOrigin.SUBMISSION,
        academic_outcome=AcademicOutcome.NOT_ACHIEVED,
    )
    assert decision.academic_outcome == AcademicOutcome.NOT_ACHIEVED
    with pytest.raises(ValidationError):
        GovernanceDecisionSnapshot(academic_outcome=AcademicOutcome.NOT_ACHIEVED)


@pytest.mark.parametrize("field", ["submission_key", "session_id", "artifact_hash", "engine", "version", "runtime_policy"])
def test_runtime_evidence_identity_mismatch_is_rejected(field: str):
    expected = {"submission_id": 1, "submission_key": "jana", "batch_id": 4, "runtime_session_id": "r1", "session_id": "s1", "artifact_hash": "abc", "engine": "gamemaker", "version": "V2", "runtime_policy": "sandbox"}
    evidence = dict(expected)
    evidence[field] = "different"
    with pytest.raises(RuntimeEvidenceIdentityMismatch, match="RUNTIME_EVIDENCE_IDENTITY_MISMATCH"):
        validate_runtime_evidence_identity(expected, evidence)


def test_legacy_is_pending_and_lms_final_guard_rejects_it():
    legacy = legacy_to_governance_snapshot({"grade_level": "U"})
    assert legacy.official_grade is None
    assert legacy.reason_code == "LEGACY_SNAPSHOT_INSUFFICIENT_FOR_FINAL_DECISION"
    with pytest.raises(ValueError, match="REQUIRES_FINAL"):
        require_final_award(legacy)
