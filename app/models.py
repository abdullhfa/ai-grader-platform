"""
SQLAlchemy database models
"""

import enum
from datetime import datetime

from sqlalchemy import (  # type: ignore
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Enum,
    ForeignKey,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class UserRole(str, enum.Enum):
    """User role enumeration"""

    USER = "user"
    ADMIN = "admin"


class UserSession(Base):
    """Persistent session storage (survives server restarts)"""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class SubmissionStatus(str, enum.Enum):
    """Submission status enumeration"""

    PENDING = "pending"
    GRADING = "grading"
    COMPLETED = "completed"
    FAILED = "failed"


class CriteriaLevel(str, enum.Enum):
    """Criteria level enumeration"""

    P1 = "P1"
    P2 = "P2"
    M1 = "M1"
    D1 = "D1"


class AssignmentStatus(str, enum.Enum):
    """Assignment status enumeration"""

    DRAFT = "draft"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class BatchStatus(str, enum.Enum):
    """Batch status enumeration"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enumeration"""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class VerificationStatus(str, enum.Enum):
    """Verification status enumeration"""

    PENDING = "pending"  # Teacher submitted, waiting for admin
    CODE_SENT = "code_sent"  # Admin entered activation code
    # Teacher entered correct code, subscription activated
    VERIFIED = "verified"
    REJECTED = "rejected"  # Admin rejected the request


class Package(Base):
    """Subscription package model"""

    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    price = Column(Float, nullable=False)
    assignment_limit = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    """User subscription model"""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    status = Column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING
    )

    transaction_id = Column(String(100))
    subjects = Column(String(500))  # Comma-separated list of subjects

    assignments_used = Column(Integer, default=0)
    assignments_limit = Column(Integer, nullable=False)

    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="subscriptions")
    package = relationship("Package")


class VerificationRequest(Base):
    """Stores verification requests from teachers, managed by admin"""

    __tablename__ = "verification_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    transaction_id = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    subjects = Column(String(500))  # Comma-separated
    amount = Column(Float, nullable=True)  # Payment amount confirmed by admin
    # Name entered by admin
    verified_teacher_name = Column(String(100), nullable=True)
    activation_code = Column(String(10), nullable=True)  # Set by admin
    status = Column(
        Enum(VerificationStatus), default=VerificationStatus.PENDING
    )
    admin_note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at: Column = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user = relationship("User", backref="verification_requests")
    package = relationship("Package")


class User(Base):
    """User account model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    open_id = Column(String(64), unique=True, nullable=True, index=True)

    # Authentication fields
    email = Column(String(320), unique=True, nullable=False, index=True)
    # Nullable for legacy users
    password_hash = Column(String(255), nullable=True)

    # Profile fields
    first_name = Column(String(100))
    last_name = Column(String(100))
    name = Column(Text)  # Full name (legacy support)
    job_title = Column(String(100))  # معلم، مشرف، مدير، منسق
    phone = Column(String(20), unique=True, nullable=True)

    login_method = Column(String(64), default="local")
    role: Column = Column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_signed_in = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    assignments = relationship("Assignment", back_populates="creator")
    submissions = relationship("Submission", back_populates="submitter")
    textbooks = relationship("Textbook", back_populates="uploader")
    batches = relationship("BatchGrading", back_populates="creator")
    assignment_links = relationship("UserAssignmentLink", back_populates="user")


class Textbook(Base):
    """Pearson textbook uploads"""

    __tablename__ = "textbooks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    file_path = Column(Text)
    total_pages = Column(Integer)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    uploader = relationship("User", back_populates="textbooks")
    assignments = relationship("Assignment", back_populates="textbook")


class Assignment(Base):
    """Assignment model"""

    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # Textbook reference
    textbook_id = Column(Integer, ForeignKey("textbooks.id"))
    page_from = Column(Integer)
    page_to = Column(Integer)

    # BTEC Unit Information (NEW - from specification)
    unit_number = Column(String(10))  # e.g., "1", "4", "21"
    unit_name = Column(String(500))  # e.g., "Programming"
    subject = Column(String(100))    # e.g., "برمجة" — matches SubjectBalance.subject
    # JSON array of criteria from specification
    unit_criteria_json = Column(Text)

    # Assignment file
    assignment_file_url = Column(Text)
    assignment_text = Column(Text)

    # Generated reference solution
    reference_solution_text = Column(Text)
    reference_solution_json = Column(Text)  # JSON format

    # Golden Hash Lock (Pearson Determinism)
    solution_hash = Column(String(64))  # SHA256 hash of reference solution
    content_hash = Column(String(64), index=True)  # SHA256 hash of input (textbook+pages+assignment_text) for deduplication
    is_locked: Column = Column(Boolean, default=False)

    status = Column(
        Enum(AssignmentStatus), default=AssignmentStatus.DRAFT, nullable=False
    )

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    creator = relationship("User", back_populates="assignments")
    textbook = relationship("Textbook", back_populates="assignments")
    criteria = relationship("GradingCriteria", back_populates="assignment")
    submissions = relationship("Submission", back_populates="assignment")
    batches = relationship("BatchGrading", back_populates="assignment")
    assignment_links = relationship("UserAssignmentLink", back_populates="assignment")


class UserAssignmentLink(Base):
    """Lets a user open / list a shared assignment (same brief guide) without duplicating rows."""

    __tablename__ = "user_assignment_links"
    __table_args__ = (
        UniqueConstraint("user_id", "assignment_id", name="uq_user_assignment_link"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(
        Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="assignment_links")
    assignment = relationship("Assignment", back_populates="assignment_links")


class GradingCriteria(Base):
    """Grading criteria model"""

    __tablename__ = "grading_criteria"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(
        Integer, ForeignKey("assignments.id"), nullable=False
    )
    criteria_level: Column = Column(String(50), nullable=False)
    criteria_name = Column(String(255), nullable=False)
    criteria_description = Column(Text, nullable=False)
    key_points = Column(Text, nullable=False)  # JSON string
    weight = Column(Integer, default=25, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    assignment = relationship("Assignment", back_populates="criteria")
    results = relationship("GradingResult", back_populates="criteria")


class BatchGrading(Base):
    """Batch grading for multiple students"""

    __tablename__ = "batch_gradings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(
        Integer, ForeignKey("assignments.id"), nullable=False
    )
    batch_name = Column(String(255), nullable=False)
    total_students = Column(Integer, default=0)
    processed_students = Column(Integer, default=0)
    status = Column(
        Enum(BatchStatus), default=BatchStatus.PENDING, nullable=False
    )
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    failure_message = Column(Text)

    # Relationships
    creator = relationship("User", back_populates="batches")
    assignment = relationship("Assignment", back_populates="batches")
    submissions = relationship("Submission", back_populates="batch")


class Submission(Base):
    """Student submission model"""

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assignment_id = Column(
        Integer, ForeignKey("assignments.id"), nullable=False
    )
    batch_id = Column(Integer, ForeignKey("batch_gradings.id"))

    student_name = Column(String(255), nullable=False)
    student_email = Column(String(320))
    student_id = Column(String(100))  # Student ID number

    submission_file_url = Column(Text)
    submission_file_path = Column(Text)
    submission_text = Column(Text)

    # Full grading payload (minus huge text) — used so Word export matches PDF report
    grading_snapshot_json = Column(Text)

    submitted_by = Column(Integer, ForeignKey("users.id"))
    status = Column(
        Enum(SubmissionStatus),
        default=SubmissionStatus.PENDING,
        nullable=False,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    assignment = relationship("Assignment", back_populates="submissions")
    batch = relationship("BatchGrading", back_populates="submissions")
    submitter = relationship("User", back_populates="submissions")
    results = relationship("GradingResult", back_populates="submission")
    summary = relationship(
        "GradingSummary", back_populates="submission", uselist=False
    )
    report = relationship(
        "StudentReport", back_populates="submission", uselist=False
    )


class GradingResult(Base):
    """Individual grading result for a criterion"""

    __tablename__ = "grading_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer, ForeignKey("submissions.id"), nullable=False
    )
    criteria_id = Column(
        Integer, ForeignKey("grading_criteria.id"), nullable=False
    )

    achieved = Column(Boolean, default=False, nullable=False)
    score = Column(Integer, default=0, nullable=False)
    max_score = Column(Integer, default=100, nullable=False)

    missing_points = Column(Text)  # JSON string
    feedback = Column(Text)

    # What's needed for next level
    next_level_requirements = Column(Text)  # JSON string

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    submission = relationship("Submission", back_populates="results")
    criteria = relationship("GradingCriteria", back_populates="results")


class GradingSummary(Base):
    """Overall grading summary for a submission"""

    __tablename__ = "grading_summaries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer, ForeignKey("submissions.id"), unique=True, nullable=False
    )

    total_score = Column(Integer, default=0, nullable=False)
    max_score = Column(Integer, default=100, nullable=False)
    percentage = Column(Float, default=0.0)
    # New field for AI detection score
    ai_likelihood = Column(Integer, default=0)

    # Plagiarism Stats
    plagiarism_max_similarity = Column(Float, default=0.0)
    plagiarism_suspicious_count = Column(Integer, default=0)

    overall_feedback = Column(Text)
    strengths = Column(Text)  # JSON string
    improvements = Column(Text)  # JSON string

    # Grade level achieved
    grade_level = Column(String(255))  # U, P, PP, M, D

    graded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    submission = relationship("Submission", back_populates="summary")


class StudentReport(Base):
    """Individual student report with detailed feedback"""

    __tablename__ = "student_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer, ForeignKey("submissions.id"), unique=True, nullable=False
    )

    report_file_url = Column(Text)  # PDF report URL
    report_file_path = Column(Text)

    # Detailed feedback for each criterion
    p1_feedback = Column(Text)
    p1_next_steps = Column(Text)

    p2_feedback = Column(Text)
    p2_next_steps = Column(Text)

    m1_feedback = Column(Text)
    m1_next_steps = Column(Text)

    d1_feedback = Column(Text)
    d1_next_steps = Column(Text)

    # Overall recommendations
    overall_recommendations = Column(Text)

    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    submission = relationship("Submission", back_populates="report")


class SolutionCache(Base):
    """Persistent cache for reference solutions — survives assignment deletion."""

    __tablename__ = "solution_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content_hash = Column(
        String(64), unique=True, index=True, nullable=False
    )
    solution_json = Column(Text, nullable=False)
    solution_hash = Column(String(64), nullable=False)
    criteria_json = Column(Text, nullable=False)  # JSON array of grading criteria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GradingCache(Base):
    """Cache for deterministic grading results"""

    __tablename__ = "grading_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fingerprint = Column(
        String(64), unique=True, index=True, nullable=False
    )  # Hash of input
    prompt_hash = Column(String(64), index=True)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    provider_used = Column(String(50))
    model_used = Column(String(50))


class PlagiarismCheck(Base):
    """Result of plagiarism comparison between two submissions"""

    __tablename__ = "plagiarism_checks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer, ForeignKey("submissions.id"), nullable=False, index=True
    )
    compared_submission_id = Column(
        Integer, ForeignKey("submissions.id"), nullable=False
    )
    assignment_id = Column(
        Integer, ForeignKey("assignments.id"), nullable=False, index=True
    )

    similarity_percentage = Column(Float, nullable=False, index=True)
    similarity_score = Column(Float, nullable=False)
    matching_segments = Column(Integer, default=0)

    is_suspicious = Column(Boolean, default=False)
    flagged_for_review = Column(Boolean, default=False)

    details_json = Column(Text)  # Detailed comparison results
    checked_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    submission = relationship(
        "Submission", foreign_keys=[submission_id], backref="plagiarism_checks"
    )
    compared_submission = relationship(
        "Submission", foreign_keys=[compared_submission_id]
    )
    assignment = relationship("Assignment", backref="plagiarism_checks")


class ActivityLog(Base):
    """Activity log for tracking all site actions"""

    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(200))
    user_email = Column(String(255))
    action = Column(String(100), nullable=False, index=True)  # login, register, grade, subscribe, export, admin_action, error
    category = Column(String(50), nullable=False, index=True)  # auth, grading, subscription, admin, export, system, error
    details = Column(Text)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    level = Column(String(20), default="info")  # info, warning, error, success
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", backref="activity_logs")


class SubjectBalance(Base):
    """Per-subject grading balance for each user.
    Each record tracks how many assignments a user can grade for a specific subject.
    """

    __tablename__ = "subject_balances"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String(100), nullable=False)          # e.g. "برمجة"
    assignments_limit = Column(Integer, default=0)         # total allowed
    assignments_used = Column(Integer, default=0)          # consumed so far
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="subject_balances")


class ContactMessage(Base):
    """Messages submitted via the contact form"""

    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False)
    message_type = Column(String(50))
    subject = Column(String(255))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
