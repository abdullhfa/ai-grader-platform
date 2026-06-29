"""Database-backed permissions store — maps users to governance roles."""
from __future__ import annotations

from typing import List, Optional, Set

from sqlalchemy.orm import Session

from app.auth.rbac_models import RbacPermission, RbacRole, RbacRolePermission, UserRbacAssignment
from app.governance.permissions import PERMISSIONS, GovernanceRole

DEFAULT_ROLE_PERMISSIONS: dict[str, Set[str]] = {
    "student": set(PERMISSIONS[GovernanceRole.STUDENT]),
    "examiner": set(PERMISSIONS[GovernanceRole.EXAMINER]),
    "senior_examiner": set(PERMISSIONS[GovernanceRole.SENIOR_EXAMINER]),
    "admin": set(PERMISSIONS[GovernanceRole.ADMIN]),
}


def seed_rbac_defaults(db: Session) -> None:
    """Seed institutional roles and permissions if empty."""
    if db.query(RbacRole).count() > 0:
        return

    role_rows = {}
    for name in DEFAULT_ROLE_PERMISSIONS:
        role = RbacRole(name=name, description=f"Institutional role: {name}")
        db.add(role)
        db.flush()
        role_rows[name] = role

    perm_rows = {}
    all_codes: Set[str] = set()
    for codes in DEFAULT_ROLE_PERMISSIONS.values():
        all_codes.update(codes)
    for code in sorted(all_codes):
        perm = RbacPermission(code=code, description=code.replace("_", " "))
        db.add(perm)
        db.flush()
        perm_rows[code] = perm

    for role_name, codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = role_rows[role_name]
        for code in codes:
            db.add(RbacRolePermission(role_id=role.id, permission_id=perm_rows[code].id))

    db.commit()


def get_user_role_names(db: Session, user_id: int) -> List[str]:
    rows = (
        db.query(RbacRole.name)
        .join(UserRbacAssignment, UserRbacAssignment.role_id == RbacRole.id)
        .filter(UserRbacAssignment.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]


def get_primary_governance_role(db: Session, user_id: int) -> Optional[str]:
    """Highest-privilege role for user."""
    names = get_user_role_names(db, user_id)
    if not names:
        return None
    priority = ["admin", "senior_examiner", "examiner", "student"]
    for role in priority:
        if role in names:
            return role
    return names[0]


def assign_user_role(
    db: Session,
    *,
    user_id: int,
    role_name: str,
    source: str = "manual",
    assigned_by: Optional[str] = None,
) -> None:
    role = db.query(RbacRole).filter(RbacRole.name == role_name).first()
    if not role:
        raise ValueError(f"unknown role: {role_name}")
    existing = (
        db.query(UserRbacAssignment)
        .filter(UserRbacAssignment.user_id == user_id, UserRbacAssignment.role_id == role.id)
        .first()
    )
    if existing:
        return
    db.add(
        UserRbacAssignment(
            user_id=user_id,
            role_id=role.id,
            source=source,
            assigned_by=assigned_by,
        )
    )
    db.commit()


def user_has_permission(db: Session, user_id: int, permission: str) -> bool:
    role_names = get_user_role_names(db, user_id)
    for name in role_names:
        try:
            role = GovernanceRole(name)
        except ValueError:
            continue
        if permission in PERMISSIONS.get(role, frozenset()):
            return True
    return False
