"""Governance Decision Snapshot v1.

This is deliberately small and fail-closed: consumers may render a draft
decision, but only a FINAL snapshot can carry an official award.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class DecisionFinality(str, Enum):
    PENDING = "PENDING"
    PROVISIONAL = "PROVISIONAL"
    FINALIZABLE = "FINALIZABLE"
    FINAL = "FINAL"


class VerificationOutcome(str, Enum):
    VERIFIED_REQUIREMENT_MET = "VERIFIED_REQUIREMENT_MET"
    VERIFIED_REQUIREMENT_FAILED = "VERIFIED_REQUIREMENT_FAILED"
    NOT_VERIFIED = "NOT_VERIFIED"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class VerificationBlockerOrigin(str, Enum):
    SYSTEM = "SYSTEM"
    SUBMISSION = "SUBMISSION"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AcademicOutcome(str, Enum):
    ELIGIBLE_FOR_ACADEMIC_EVALUATION = "ELIGIBLE_FOR_ACADEMIC_EVALUATION"
    NOT_ACHIEVED = "NOT_ACHIEVED"
    PENDING = "PENDING"


def resolve_academic_outcome(*, criterion_requires_runtime: bool,
                             verification_outcome: VerificationOutcome | None,
                             blocker_origin: VerificationBlockerOrigin) -> AcademicOutcome:
    """Map verification to academic state without treating system absence as failure."""
    if not criterion_requires_runtime:
        return AcademicOutcome.ELIGIBLE_FOR_ACADEMIC_EVALUATION
    if verification_outcome == VerificationOutcome.VERIFIED_REQUIREMENT_MET:
        return AcademicOutcome.ELIGIBLE_FOR_ACADEMIC_EVALUATION
    if verification_outcome == VerificationOutcome.VERIFIED_REQUIREMENT_FAILED:
        return AcademicOutcome.NOT_ACHIEVED
    return AcademicOutcome.PENDING


class GovernanceDecisionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    contract_name: str = "GovernanceDecisionSnapshot"
    contract_version: str = "1.0"
    schema_version: int = 1
    decision_finality: DecisionFinality = DecisionFinality.PENDING
    calculated_band: str = "U"
    official_grade: Optional[str] = None
    award_status: str = "PENDING_HUMAN_REVIEW"
    is_final: bool = False
    runtime_verification_status: str = "NOT_VERIFIED"
    verification_outcome: VerificationOutcome = VerificationOutcome.NOT_VERIFIED
    verification_blocker_origin: VerificationBlockerOrigin = VerificationBlockerOrigin.UNKNOWN
    academic_outcome: AcademicOutcome = AcademicOutcome.PENDING
    final_award_blocked: bool = True
    human_review_required: bool = True
    reason_code: str = "RUNTIME_ENVIRONMENT_UNSUPPORTED"
    criterion_requires_runtime: bool = True
    engine_id: str = "gamemaker"
    selected_version: Optional[str] = None

    @model_validator(mode="after")
    def enforce_invariants(self) -> "GovernanceDecisionSnapshot":
        if self.contract_name != "GovernanceDecisionSnapshot" or self.contract_version != "1.0" or self.schema_version != 1:
            raise ValueError("unsupported GovernanceDecisionSnapshot contract")
        final = self.decision_finality == DecisionFinality.FINAL
        if self.is_final != final:
            raise ValueError("is_final and decision_finality must agree")
        if final:
            if not self.official_grade or self.award_status != "FINAL" or self.human_review_required:
                raise ValueError("FINAL requires official grade, FINAL award status, and no human review")
        else:
            if self.official_grade is not None or self.award_status == "FINAL":
                raise ValueError("non-final snapshots cannot carry an official grade or FINAL award")
        if self.award_status == "PENDING_HUMAN_REVIEW":
            if self.decision_finality != DecisionFinality.PENDING or not self.human_review_required or not self.final_award_blocked:
                raise ValueError("pending review must be a blocked PENDING decision")
        expected = resolve_academic_outcome(
            criterion_requires_runtime=self.criterion_requires_runtime,
            verification_outcome=self.verification_outcome,
            blocker_origin=self.verification_blocker_origin,
        )
        if self.academic_outcome != expected:
            raise ValueError("academic outcome is inconsistent with verification outcome")
        return self


# Temporary source compatibility for callers which imported the previous name.
FinalizedGovernanceSnapshot = GovernanceDecisionSnapshot


class RuntimeEvidenceIdentityMismatch(ValueError):
    code = "RUNTIME_EVIDENCE_IDENTITY_MISMATCH"


def validate_runtime_evidence_identity(expected: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    """Reject rather than merge evidence whose immutable identity differs."""
    for field in ("submission_id", "submission_key", "batch_id", "runtime_session_id", "session_id", "artifact_hash", "engine", "version", "runtime_policy"):
        wanted, actual = expected.get(field), evidence.get(field)
        if wanted is not None and actual != wanted:
            raise RuntimeEvidenceIdentityMismatch(f"{RuntimeEvidenceIdentityMismatch.code}: {field}")


def legacy_to_governance_snapshot(_: Mapping[str, Any]) -> GovernanceDecisionSnapshot:
    """Ambiguous historical records are never guessed into a final award."""
    return GovernanceDecisionSnapshot(
        verification_blocker_origin=VerificationBlockerOrigin.UNKNOWN,
        reason_code="LEGACY_SNAPSHOT_INSUFFICIENT_FOR_FINAL_DECISION",
    )


def require_final_award(snapshot: GovernanceDecisionSnapshot | Mapping[str, Any]) -> GovernanceDecisionSnapshot:
    decision = snapshot if isinstance(snapshot, GovernanceDecisionSnapshot) else GovernanceDecisionSnapshot.model_validate(snapshot)
    if decision.decision_finality != DecisionFinality.FINAL:
        raise ValueError("FINAL_AWARD_RECORD_REQUIRES_FINAL_GOVERNANCE_DECISION")
    return decision
