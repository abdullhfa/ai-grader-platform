"""Database-backed RBAC for institutional governance."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def _utc_now() -> datetime:
    """Naive UTC for legacy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RbacRole(Base):
    __tablename__ = "rbac_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)


class RbacPermission(Base):
    __tablename__ = "rbac_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)


class RbacRolePermission(Base):
    __tablename__ = "rbac_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("rbac_roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Integer, ForeignKey("rbac_permissions.id", ondelete="CASCADE"), nullable=False)


class UserRbacAssignment(Base):
    __tablename__ = "user_rbac_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("rbac_roles.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(32), default="manual", nullable=False)
    assigned_by = Column(String(320), nullable=True)
    assigned_at = Column(DateTime, default=_utc_now, nullable=False)

    role = relationship("RbacRole")


class IdentityAuditLog(Base):
    __tablename__ = "identity_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String(320), nullable=True)
    action = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=True)
    trace_id = Column(String(64), nullable=True, index=True)
    metadata_json = Column(String(2000), nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
