"""Subscription helpers — shared by main and routers."""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.grading_mode_policy import resolve_grading_policy


def get_active_subscription(db: Session, user_id: int):
    return (
        db.query(models.Subscription)
        .filter(
            models.Subscription.user_id == user_id,
            models.Subscription.status.in_(
                [models.SubscriptionStatus.ACTIVE, "active", "ACTIVE"]
            ),
        )
        .order_by(models.Subscription.created_at.desc())
        .first()
    )


def get_subscription_info(db: Session, user_id: int) -> dict:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is not None and user.role == models.UserRole.ADMIN:
        return {
            "has_subscription": True,
            "remaining": 9999,
            "package_name": "Admin (غير محدود)",
            "assignments_limit": 9999,
            "assignments_used": 0,
            "subscription_id": 0,
            "grading_mode": "deep",
            "grading_profile_label": "Admin — Full verification",
            "grading_profile_description": "صلاحيات إدارية — تحقق كامل بدون قيود الباقة.",
        }

    balances = (
        db.query(models.SubjectBalance)
        .filter(models.SubjectBalance.user_id == user_id)
        .all()
    )
    if balances:
        total_limit = sum(b.assignments_limit or 0 for b in balances)
        total_used = sum(b.assignments_used or 0 for b in balances)
        total_remaining = max(0, total_limit - total_used)
        subjects_str = "|".join(str(b.subject) for b in balances if b.subject)
        subject_details = [
            {
                "subject": b.subject,
                "limit": b.assignments_limit or 0,
                "used": b.assignments_used or 0,
                "remaining": max(0, (b.assignments_limit or 0) - (b.assignments_used or 0)),
            }
            for b in balances
        ]
        sub = get_active_subscription(db, user_id)
        pkg_name = ""
        if sub:
            pkg = db.query(models.Package).filter(models.Package.id == sub.package_id).first()
            pkg_name = pkg.name if pkg else ""
        policy = resolve_grading_policy(pkg_name)
        return {
            "has_subscription": total_remaining > 0,
            "remaining": total_remaining,
            "package_name": pkg_name,
            "assignments_limit": total_limit,
            "assignments_used": total_used,
            "subscription_id": sub.id if sub else 0,
            "subjects": subjects_str,
            "subject_details": subject_details,
            "grading_mode": policy["grading_mode"],
            "grading_profile_label": policy["label_ar"],
            "grading_profile_description": policy.get("description_ar") or policy["label_ar"],
        }

    sub = get_active_subscription(db, user_id)
    if not sub:
        return {
            "has_subscription": False,
            "remaining": 0,
            "package_name": "",
            "assignments_limit": 0,
            "assignments_used": 0,
            "grading_mode": "deep",
            "grading_profile_label": "افتراضي — تحقق كامل",
            "grading_profile_description": "تحقق كامل — اشترِ باقة Basic أو Pro لمعرفة الفرق بالتفصيل.",
        }
    remaining = (sub.assignments_limit or 0) - (sub.assignments_used or 0)
    pkg = db.query(models.Package).filter(models.Package.id == sub.package_id).first()
    old_subject_details = []
    if sub.subjects:
        for subj in re.split(r"[,|]", str(sub.subjects)):
            subj = subj.strip()
            if subj:
                old_subject_details.append({
                    "subject": subj,
                    "limit": sub.assignments_limit or 0,
                    "used": sub.assignments_used or 0,
                    "remaining": max(remaining, 0),
                })
    policy = resolve_grading_policy(pkg.name if pkg else "")
    return {
        "has_subscription": True,
        "remaining": max(remaining, 0),
        "package_name": pkg.name if pkg else "",
        "assignments_limit": sub.assignments_limit or 0,
        "assignments_used": sub.assignments_used or 0,
        "subscription_id": sub.id,
        "subjects": sub.subjects or "",
        "subject_details": old_subject_details,
        "grading_mode": policy["grading_mode"],
        "grading_profile_label": policy["label_ar"],
        "grading_profile_description": policy.get("description_ar") or policy["label_ar"],
    }
