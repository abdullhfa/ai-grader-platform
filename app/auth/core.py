"""Legacy authentication core — sessions, passwords, Google OAuth."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

try:
    import bcrypt  # type: ignore

    USE_BCRYPT = True
except ImportError:
    USE_BCRYPT = False

from app.database import SessionLocal  # type: ignore
from app.models import User, UserRole, UserSession  # type: ignore

SESSION_TIMEOUT = timedelta(hours=24)


def _utc_now() -> datetime:
    """Naive UTC for legacy DateTime columns (DB stores UTC without tz)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _touch_last_signed_in(user: User) -> None:
    setattr(user, "last_signed_in", _utc_now())


def _link_google_identity(user: User, google_id: str) -> None:
    setattr(user, "open_id", google_id)
    setattr(user, "login_method", "google")
    _touch_last_signed_in(user)


def _get_db():
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def create_session(user_id: int, *, trace_id: Optional[str] = None) -> str:
    session_id = secrets.token_urlsafe(32)
    db = _get_db()
    try:
        sess = UserSession(
            session_id=session_id,
            user_id=user_id,
            created_at=_utc_now(),
            expires_at=_utc_now() + SESSION_TIMEOUT,
        )
        db.add(sess)
        db.commit()
    finally:
        db.close()
    if trace_id:
        try:
            from app.auth.session_manager import attach_trace_to_session

            attach_trace_to_session(session_id, trace_id)
        except Exception:
            pass
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    db = _get_db()
    try:
        sess = db.query(UserSession).filter(UserSession.session_id == session_id).first()
        if not sess:
            return None
        if _utc_now() > sess.expires_at:
            db.delete(sess)
            db.commit()
            return None
        return {
            "user_id": sess.user_id,
            "created_at": sess.created_at,
            "expires_at": sess.expires_at,
        }
    finally:
        db.close()


def delete_session(session_id: str):
    db = _get_db()
    try:
        sess = db.query(UserSession).filter(UserSession.session_id == session_id).first()
        if sess:
            db.delete(sess)
            db.commit()
    finally:
        db.close()


def hash_password(password: str) -> str:
    if USE_BCRYPT:
        salt = bcrypt.gensalt()  # type: ignore
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")  # type: ignore
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, password_hash: str) -> bool:
    if USE_BCRYPT and password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))  # type: ignore
    if "$" in password_hash:
        salt, hashed = password_hash.split("$", 1)
        return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
    return False


def get_current_user_id(request: Request) -> Optional[int]:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    session = get_session(session_id)
    if not session:
        return None
    return session["user_id"]


def get_current_user(request: Request, db: Optional[Session] = None) -> Optional[User]:
    user_id = get_current_user_id(request)
    if not user_id or db is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def user_is_admin(user: Optional[User]) -> bool:
    """True when user has admin role (enum or legacy string)."""
    if user is None or user.role is None:
        return False
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return str(role).strip().lower() == "admin"


def register_user(
    db: Session,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    job_title: Optional[str] = None,
    phone: Optional[str] = None,
) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("البريد الإلكتروني مسجل مسبقاً")

    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        name=f"{first_name} {last_name}",
        job_title=job_title,
        phone=phone,
        login_method="local",
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    _touch_last_signed_in(user)
    db.commit()
    return user


def google_login_or_register(
    db: Session,
    google_id: str,
    email: str,
    first_name: str,
    last_name: str,
) -> Optional[User]:
    user = db.query(User).filter(User.open_id == google_id).first()
    if user:
        _touch_last_signed_in(user)
        db.commit()
        return user

    user = db.query(User).filter(User.email == email).first()
    if user:
        _link_google_identity(user, google_id)
        db.commit()
        return user

    user = User(
        open_id=google_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        name=f"{first_name} {last_name}",
        login_method="google",
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
