"""
Database models for the BTEC Comprehensive Assessment System.
Covers all 5 phases: Brief Analysis, Reference Solution, Rubric,
Student Evaluation, and Internal Verification.
"""

import enum
from datetime import datetime

from sqlalchemy import (  # type: ignore
    Column, Integer, String, Text, DateTime,
    Boolean, Enum, ForeignKey, Float,
)
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


# ═══════════════════════════════════════════════════════
# Enumerations
# ═══════════════════════════════════════════════════════

class BTECPhase(str, enum.Enum):
    PRE_ASSIGNMENT_VALIDATION = "pre_assignment_validation"
    BRIEF_ANALYSIS = "brief_analysis"
    REFERENCE_SOLUTION = "reference_solution"
    RUBRIC_CREATION = "rubric_creation"
    STUDENT_EVALUATION = "student_evaluation"
    INTERNAL_VERIFICATION = "internal_verification"


class PreValidationStatus(str, enum.Enum):
    VALIDATED = "validated"
    NEEDS_REVISION = "needs_revision"
    INCOMPLETE = "incomplete"


class BTECGradeLevel(str, enum.Enum):
    NOT_ACHIEVED = "not_achieved"
    PASS = "pass"
    MERIT = "merit"
    DISTINCTION = "distinction"
    REFER = "refer"


class BriefValidityStatus(str, enum.Enum):
    VALID = "valid"
    MINOR_ISSUES = "minor_issues"
    MAJOR_ISSUES = "major_issues"


class IVDecision(str, enum.Enum):
    APPROVED = "approved"
    APPROVED_WITH_AMENDMENTS = "approved_with_amendments"
    REQUIRES_REVISION = "requires_revision"


# ═══════════════════════════════════════════════════════
# Phase 0: Pre-Assignment Validation & Teacher Reference Guide
# ═══════════════════════════════════════════════════════

class BTECPreAssignmentValidation(Base):
    """Phase 0: Pre-Assignment Validation + Teacher Reference Guide (generated once)"""
    __tablename__ = "btec_pre_assignment_validations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Assignment hash for dedup/caching — ensures generation only once
    assignment_hash = Column(String(64), unique=True, index=True)

    # Input data (stored for reference)
    assignment_text_stored = Column(Text)
    unit_name = Column(String(255))
    unit_number = Column(String(50))

    # Pre-validation results
    validation_status = Column(
        Enum(PreValidationStatus), default=PreValidationStatus.NEEDS_REVISION
    )
    brief_validity = Column(Text)        # JSON: brief correctness
    criteria_clarity = Column(Text)      # JSON: criteria clarity check
    references_check = Column(Text)      # JSON: references availability
    lo_alignment = Column(Text)          # JSON: LO alignment check
    validation_summary = Column(Text)    # Summary in Arabic

    # 10-Section Teacher Reference Guide
    section_1_assignment_analysis = Column(Text)       # JSON
    section_2_learning_aims = Column(Text)              # JSON
    section_3_criteria_breakdown = Column(Text)         # JSON
    section_4_theoretical = Column(Text)                # JSON
    section_5_practical = Column(Text)                  # JSON
    section_6_deliverables = Column(Text)               # JSON
    section_7_evidence = Column(Text)                   # JSON
    section_8_grade_interpretation = Column(Text)       # JSON
    section_9_common_errors = Column(Text)              # JSON
    section_10_marking_checklist = Column(Text)         # JSON

    # Full compiled document
    full_document = Column(Text)             # Complete JSON
    document_hash = Column(String(64))       # SHA256 integrity hash

    # Standard student submission structure
    submission_structure = Column(Text)      # JSON

    is_locked = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignment = relationship("Assignment", foreign_keys=[assignment_id])
    creator = relationship("User")


# ═══════════════════════════════════════════════════════
# Phase 1: Assignment Brief Analysis
# ═══════════════════════════════════════════════════════

class BTECBriefAnalysis(Base):
    """Phase 1: Assignment Brief validation and analysis"""
    __tablename__ = "btec_brief_analyses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Validity status
    validity_status = Column(
        Enum(BriefValidityStatus),
        default=BriefValidityStatus.VALID
    )

    # Learning Aims coverage (JSON)
    learning_aims_analysis = Column(Text)  # JSON
    # Assessment Criteria clarity (JSON)
    criteria_clarity_analysis = Column(Text)  # JSON
    # Professional scenario analysis (JSON)
    scenario_analysis = Column(Text)  # JSON
    # Feasibility assessment (JSON)
    feasibility_analysis = Column(Text)  # JSON
    # Evidence requirements (JSON)
    evidence_requirements = Column(Text)  # JSON
    # Issues and ambiguities (JSON)
    issues_found = Column(Text)  # JSON
    # Compliance verification (JSON)
    compliance_check = Column(Text)  # JSON
    # Mapping matrix (JSON)
    mapping_matrix = Column(Text)  # JSON

    # Summary
    summary_report = Column(Text)  # Full HTML/Markdown report
    recommendations = Column(Text)  # JSON list of recommendations

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignment = relationship("Assignment")
    creator = relationship("User")


# ═══════════════════════════════════════════════════════
# Phase 2: Teacher Reference Solution
# ═══════════════════════════════════════════════════════

class BTECReferenceSolution(Base):
    """Phase 2: Comprehensive Teacher Reference Solution"""
    __tablename__ = "btec_reference_solutions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 10 Sections stored as JSON
    section_1_assignment_analysis = Column(Text)      # JSON
    section_2_learning_aim_interpretation = Column(Text)  # JSON
    section_3_criteria_breakdown = Column(Text)        # JSON
    section_4_theoretical_requirements = Column(Text)  # JSON
    section_5_practical_requirements = Column(Text)    # JSON
    section_6_expected_deliverables = Column(Text)     # JSON
    section_7_evidence_authenticity = Column(Text)     # JSON
    section_8_grade_interpretation = Column(Text)      # JSON
    section_9_common_errors = Column(Text)             # JSON
    section_10_marking_checklist = Column(Text)        # JSON

    # Full compiled document
    full_document = Column(Text)  # Complete HTML/Markdown
    solution_hash = Column(String(64))  # SHA256 for integrity

    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignment = relationship("Assignment")
    creator = relationship("User")
    rubrics = relationship("BTECRubric", back_populates="reference_solution")


# ═══════════════════════════════════════════════════════
# Phase 3: Rubric
# ═══════════════════════════════════════════════════════

class BTECRubric(Base):
    """Phase 3: Assessment Rubric"""
    __tablename__ = "btec_rubrics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    reference_solution_id = Column(
        Integer, ForeignKey("btec_reference_solutions.id"), nullable=False
    )
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Per-criterion descriptors (JSON array)
    criteria_descriptors = Column(Text)  # JSON
    # Weighting system (JSON)
    weighting_system = Column(Text)  # JSON
    # Evidence mapping (JSON)
    evidence_mapping = Column(Text)  # JSON
    # Common misconceptions (JSON)
    common_misconceptions = Column(Text)  # JSON
    # Marking tips (JSON)
    marking_tips = Column(Text)  # JSON

    # Full rubric document
    full_rubric = Column(Text)  # Complete HTML table

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignment = relationship("Assignment")
    reference_solution = relationship("BTECReferenceSolution", back_populates="rubrics")
    creator = relationship("User")
    evaluations = relationship("BTECStudentEvaluation", back_populates="rubric")


# ═══════════════════════════════════════════════════════
# Phase 4: Student Evaluation
# ═══════════════════════════════════════════════════════

class BTECStudentEvaluation(Base):
    """Phase 4: Comprehensive Student Work Evaluation"""
    __tablename__ = "btec_student_evaluations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    rubric_id = Column(Integer, ForeignKey("btec_rubrics.id"), nullable=False)
    assessed_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Structure analysis (JSON)
    structure_analysis = Column(Text)  # JSON
    # Per-criterion evaluation (JSON array)
    criteria_evaluations = Column(Text)  # JSON
    # Plagiarism & authenticity (JSON)
    authenticity_check = Column(Text)  # JSON
    # AI content detection (JSON)
    ai_detection = Column(Text)  # JSON
    # Similarity analysis (JSON)
    similarity_analysis = Column(Text)  # JSON

    # Overall grades
    final_grade = Column(
        Enum(BTECGradeLevel), default=BTECGradeLevel.NOT_ACHIEVED
    )
    confidence_score = Column(Float, default=0.0)
    ai_risk_score = Column(Float, default=0.0)
    similarity_score = Column(Float, default=0.0)

    # Per-criterion grades (JSON: {"A.P1": "pass", "A.M1": "merit", ...})
    criterion_grades = Column(Text)  # JSON

    # Detailed feedback
    strengths = Column(Text)
    weaknesses = Column(Text)
    improvements = Column(Text)
    next_steps = Column(Text)

    # Full assessor report
    assessor_report = Column(Text)  # Full HTML/Markdown

    # Report PDF path
    report_pdf_path = Column(Text)

    # Local algorithm analysis (JSON — from btec_algorithms.py)
    local_analysis = Column(Text)  # JSON: {local_similarity, local_ai_detection, local_grade}

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    submission = relationship("Submission")
    rubric = relationship("BTECRubric", back_populates="evaluations")
    assessor = relationship("User")


# ═══════════════════════════════════════════════════════
# Phase 5: Internal Verification
# ═══════════════════════════════════════════════════════

class BTECInternalVerification(Base):
    """Phase 5: IV Review of Assessment Quality"""
    __tablename__ = "btec_internal_verifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Sample verification (JSON)
    sample_verification = Column(Text)  # JSON
    # Consistency check (JSON)
    consistency_check = Column(Text)  # JSON
    # Evidence verification (JSON)
    evidence_verification = Column(Text)  # JSON
    # Feedback quality (JSON)
    feedback_quality = Column(Text)  # JSON
    # Plagiarism checks (JSON)
    plagiarism_checks_review = Column(Text)  # JSON
    # Academic integrity (JSON)
    academic_integrity = Column(Text)  # JSON
    # Issues & recommendations (JSON array)
    issues_and_recommendations = Column(Text)  # JSON

    # IV Decision
    iv_decision = Column(
        Enum(IVDecision), default=IVDecision.REQUIRES_REVISION
    )

    # Evaluation IDs reviewed (JSON array of IDs)
    evaluation_ids_reviewed = Column(Text)  # JSON

    # Full IV report
    full_report = Column(Text)  # HTML/Markdown

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignment = relationship("Assignment")
    verifier = relationship("User")
