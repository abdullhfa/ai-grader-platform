"""
Database configuration and session management
"""
import os
from sqlalchemy import create_engine  # type: ignore
from sqlalchemy.ext.declarative import declarative_base  # type: ignore
from sqlalchemy.orm import sessionmaker  # type: ignore
from dotenv import load_dotenv  # type: ignore

load_dotenv()

# Handle MySQL driver availability
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_grader.db")
if "mysql" in DATABASE_URL:
    try:
        if "+pymysql" in DATABASE_URL:
            import pymysql  # type: ignore
            pymysql.install_as_MySQLdb()
        import MySQLdb  # type: ignore # noqa: F401
    except ImportError:
        try:
            import pymysql  # type: ignore
            pymysql.install_as_MySQLdb()
        except ImportError:
            DATABASE_URL = "sqlite:///./ai_grader.db"
            print("  [WARN] MySQL driver (mysqlclient or pymysql) not found, using SQLite instead")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        echo=os.getenv("DEBUG", "False").lower() == "true"
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=os.getenv("DEBUG", "False").lower() == "true"
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables
    """
    from app.models import (  # type: ignore # noqa: F401
        User, Assignment, GradingCriteria, Submission, GradingResult,
        GradingSummary, GradingCache, Package, Subscription,
        VerificationRequest, StudentReport, BatchGrading, Textbook,
        PlagiarismCheck, SubjectBalance, UserAssignmentLink
    )
    import app.btec_models  # type: ignore # noqa: F401
    from app.auth.rbac_models import (  # noqa: F401
        IdentityAuditLog,
        RbacPermission,
        RbacRole,
        RbacRolePermission,
        UserRbacAssignment,
    )

    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

    try:
        from app.auth.permissions_store import seed_rbac_defaults

        _db = SessionLocal()
        try:
            seed_rbac_defaults(_db)
        finally:
            _db.close()
    except Exception as exc:
        print(f"  [WARN] RBAC seed skipped: {exc}")

    # Migrate: add missing columns if needed (safe for SQLite / MySQL)
    from sqlalchemy import inspect as sa_inspect, text  # type: ignore
    inspector = sa_inspect(engine)

    # --- btec_student_evaluations: local_analysis ---
    if "btec_student_evaluations" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("btec_student_evaluations")]
        if "local_analysis" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE btec_student_evaluations ADD COLUMN local_analysis TEXT")
                )
            print("  [OK] Added local_analysis column to btec_student_evaluations")

    # --- assignments: content_hash, solution_hash, is_locked ---
    if "assignments" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("assignments")]
        with engine.begin() as conn:
            if "content_hash" not in cols:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN content_hash VARCHAR(64)"))
                print("  [OK] Added content_hash column to assignments")
            if "solution_hash" not in cols:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN solution_hash VARCHAR(64)"))
                print("  [OK] Added solution_hash column to assignments")
            if "is_locked" not in cols:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN is_locked BOOLEAN DEFAULT 0"))
                print("  [OK] Added is_locked column to assignments")

    # --- btec_pre_assignment_validations: assignment_hash, is_locked ---
    if "btec_pre_assignment_validations" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("btec_pre_assignment_validations")]
        with engine.begin() as conn:
            if "assignment_hash" not in cols:
                conn.execute(text("ALTER TABLE btec_pre_assignment_validations ADD COLUMN assignment_hash VARCHAR(64)"))
                print("  [OK] Added assignment_hash column to btec_pre_assignment_validations")
            if "is_locked" not in cols:
                conn.execute(text("ALTER TABLE btec_pre_assignment_validations ADD COLUMN is_locked BOOLEAN DEFAULT 1"))
                print("  [OK] Added is_locked column to btec_pre_assignment_validations")

    # --- btec_reference_solutions: solution_hash, is_locked ---
    if "btec_reference_solutions" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("btec_reference_solutions")]
        with engine.begin() as conn:
            if "solution_hash" not in cols:
                conn.execute(text("ALTER TABLE btec_reference_solutions ADD COLUMN solution_hash VARCHAR(64)"))
                print("  [OK] Added solution_hash column to btec_reference_solutions")
            if "is_locked" not in cols:
                conn.execute(text("ALTER TABLE btec_reference_solutions ADD COLUMN is_locked BOOLEAN DEFAULT 0"))
                print("  [OK] Added is_locked column to btec_reference_solutions")

    # --- activity_logs: user_email, user_agent ---
    if "activity_logs" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("activity_logs")]
        with engine.begin() as conn:
            if "user_email" not in cols:
                conn.execute(text("ALTER TABLE activity_logs ADD COLUMN user_email VARCHAR(255)"))
                print("  [OK] Added user_email column to activity_logs")
            if "user_agent" not in cols:
                conn.execute(text("ALTER TABLE activity_logs ADD COLUMN user_agent VARCHAR(500)"))
                print("  [OK] Added user_agent column to activity_logs")

    # --- assignments: subject (per-subject balance matching) ---
    if "assignments" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("assignments")]
        if "subject" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN subject VARCHAR(100)"))
            print("  [OK] Added subject column to assignments")

    # --- submissions: grading_snapshot_json (Word export parity with PDF) ---
    if "submissions" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("submissions")]
        if "grading_snapshot_json" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN grading_snapshot_json TEXT"))
            print("  [OK] Added grading_snapshot_json column to submissions")

    # --- batch_gradings: failure_message ---
    if "batch_gradings" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("batch_gradings")]
        if "failure_message" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE batch_gradings ADD COLUMN failure_message TEXT"))
            print("  [OK] Added failure_message column to batch_gradings")

    seed_packages()


def _set_package_attrs(pkg: object, **attrs: object) -> None:
    """Assign ORM fields without Pyrefly Column descriptor noise."""
    for key, value in attrs.items():
        setattr(pkg, key, value)


def seed_packages():
    """Sync subscription packages with the canonical marketing catalog."""
    from app.models import Package  # type: ignore
    from app.package_catalog import ALL_PACKAGE_CATALOGS, assignment_subtitle  # type: ignore

    PACKAGE_RENAME_MAP = {
        "الباقة التجريبية": "Trial",
        "الباقة الأساسية": "Starter",
        "الباقة المتقدمة": "Advanced",
        "الباقة الاحترافية": "Ultimate",
        "طالب - 2 واجبات لمهمة واحدة": "Student Basic",
        "طالب - 6 واجبات لمهمتين": "Student Standard",
        "طالب - 8 واجبات لمهمة واحدة": "Student Premium",
        "طالب - 14 واجبات لمهمتين": "Student Pro",
    }

    db = SessionLocal()
    try:
        for old_name, new_name in PACKAGE_RENAME_MAP.items():
            old_pkg = db.query(Package).filter(Package.name == old_name).first()
            if old_pkg is None:
                continue
            clash = (
                db.query(Package)
                .filter(Package.name == new_name, Package.id != old_pkg.id)
                .first()
            )
            if clash is None:
                _set_package_attrs(old_pkg, name=new_name)

        catalog_names = {spec["name"] for spec in ALL_PACKAGE_CATALOGS}
        for spec in ALL_PACKAGE_CATALOGS:
            limit = int(spec["assignment_limit"])
            subtitle = spec.get("subtitle")
            if subtitle is None:
                if str(spec["name"]).startswith("Student "):
                    subtitle = spec.get("card_title") or spec["name"].replace("Student ", "", 1)
                else:
                    subtitle = assignment_subtitle(limit)
            pkg = db.query(Package).filter(Package.name == spec["name"]).first()
            if pkg is None:
                pkg = Package(name=spec["name"])
                db.add(pkg)
            _set_package_attrs(
                pkg,
                description=str(subtitle),
                price=float(spec["price"]),
                assignment_limit=limit,
                is_active=True,
                is_featured=bool(spec.get("is_featured", False)),
            )

        for pkg in db.query(Package).all():
            if pkg.name not in catalog_names:
                _set_package_attrs(pkg, is_active=False)

        # Keep one row per catalog name (older DBs may have duplicate names).
        for spec in ALL_PACKAGE_CATALOGS:
            name = spec["name"]
            matches = (
                db.query(Package)
                .filter(Package.name == name)
                .order_by(Package.id.asc())
                .all()
            )
            if len(matches) <= 1:
                continue
            keeper = matches[0]
            subtitle = spec.get("subtitle")
            if subtitle is None:
                if str(name).startswith("Student "):
                    subtitle = spec.get("card_title") or name.replace("Student ", "", 1)
                else:
                    subtitle = assignment_subtitle(int(spec["assignment_limit"]))
            _set_package_attrs(
                keeper,
                is_active=True,
                price=float(spec["price"]),
                assignment_limit=int(spec["assignment_limit"]),
                is_featured=bool(spec.get("is_featured", False)),
                description=str(subtitle),
            )
            for duplicate in matches[1:]:
                _set_package_attrs(duplicate, is_active=False)

        db.commit()
        active = db.query(Package).filter(Package.is_active.is_(True)).count()
        print(f"[OK] Synced {active} subscription packages")
    except Exception as e:
        print(f"[ERROR] Package seeding error: {e}")
        db.rollback()
    finally:
        db.close()


def _build_package_rows(db, catalog, feature_lines_fn=None):
    """Build UI rows for a package catalog spec list."""
    from app.models import Package  # type: ignore
    from app.package_catalog import assignment_subtitle, package_feature_lines  # type: ignore
    from app.grading_mode_policy import resolve_grading_policy  # type: ignore

    lines_fn = feature_lines_fn or package_feature_lines
    by_name = {
        p.name: p
        for p in db.query(Package).filter(Package.is_active.is_(True)).all()
    }
    rows = []
    for spec in catalog:
        pkg = by_name.get(spec["name"])
        if pkg is None:
            continue
        limit = int(pkg.assignment_limit)
        _features = list(lines_fn(limit))
        _policy = resolve_grading_policy(pkg.name)
        _grading_line = (
            _policy.get("description_ar")
            or f"وضع التصحيح: {_policy.get('label_ar', 'Default')}"
        )
        # Second bullet — visible under assignment count (not buried at the end).
        _features.insert(1, _grading_line)
        _subtitle = spec.get("subtitle") or assignment_subtitle(limit)
        _label = (_policy.get("label_ar") or "").strip()
        if _label and spec.get("name") in (
            "Basic",
            "Pro",
            "Student Basic",
            "Student Pro",
        ):
            _subtitle = f"{_subtitle} · {_label}"
        rows.append(
            {
                "package": pkg,
                "theme": int(spec.get("theme", 0)),
                "card_title": spec.get("card_title") or pkg.name,
                "subtitle": _subtitle,
                "features": _features,
            }
        )
    return rows


def get_package_rows(db):
    """Return teacher/school packages in catalog display order."""
    from app.package_catalog import PACKAGE_CATALOG  # type: ignore

    return _build_package_rows(db, PACKAGE_CATALOG)


def get_student_package_rows(db):
    """Return student audience packages with full feature list for UI."""
    from app.models import Package  # type: ignore
    from app.package_catalog import (  # type: ignore
        STUDENT_PACKAGE_CATALOG,
        assignment_subtitle,
        student_package_feature_lines,
    )
    from app.grading_mode_policy import resolve_grading_policy  # type: ignore

    by_name = {
        p.name: p
        for p in db.query(Package).filter(Package.is_active.is_(True)).all()
    }
    rows = []
    for spec in STUDENT_PACKAGE_CATALOG:
        pkg = by_name.get(spec["name"])
        if pkg is None:
            continue
        limit = int(pkg.assignment_limit)
        _features = list(student_package_feature_lines(limit))
        _policy = resolve_grading_policy(pkg.name)
        _grading_line = (
            _policy.get("description_ar")
            or f"وضع التصحيح: {_policy.get('label_ar', 'Default')}"
        )
        _features.insert(1, _grading_line)
        _subtitle = spec.get("subtitle") or assignment_subtitle(limit)
        _label = (_policy.get("label_ar") or "").strip()
        if _label and spec.get("name") in ("Student Basic", "Student Pro"):
            _subtitle = f"{_subtitle} · {_label}"
        rows.append(
            {
                "package": pkg,
                "theme": int(spec.get("theme", 0)),
                "card_title": spec.get("card_title") or pkg.name.replace("Student ", "", 1),
                "subtitle": _subtitle,
                "features": _features,
            }
        )

    if not rows:
        spec_by_limit = {int(s["assignment_limit"]): s for s in STUDENT_PACKAGE_CATALOG}
        legacy_prefixes = ("طالب - ", "Student ")
        for idx, pkg in enumerate(
            sorted(
                (
                    p
                    for p in by_name.values()
                    if p.name.startswith(legacy_prefixes)
                ),
                key=lambda p: (p.price, p.assignment_limit),
            )
        ):
            limit = int(pkg.assignment_limit)
            spec = spec_by_limit.get(limit, {})
            _features = list(student_package_feature_lines(limit))
            _policy = resolve_grading_policy(pkg.name)
            _grading_line = (
                _policy.get("description_ar")
                or f"وضع التصحيح: {_policy.get('label_ar', 'Default')}"
            )
            _features.insert(1, _grading_line)
            rows.append(
                {
                    "package": pkg,
                    "theme": int(spec.get("theme", idx % 4)),
                    "card_title": spec.get("card_title")
                    or pkg.name.replace("Student ", "", 1),
                    "subtitle": spec.get("subtitle")
                    or pkg.description
                    or assignment_subtitle(limit),
                    "features": _features,
                }
            )

    return rows


if __name__ == "__main__":
    init_db()
