"""Map IdP claims to institutional governance roles."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _load_group_map() -> Dict[str, str]:
    raw = os.environ.get("AI_GRADER_SSO_GROUP_ROLE_MAP", "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k).lower(): str(v).lower() for k, v in data.items()}
    except json.JSONDecodeError:
        pass
    mapping: Dict[str, str] = {}
    for part in raw.split(","):
        if ":" in part:
            grp, role = part.split(":", 1)
            mapping[grp.strip().lower()] = role.strip().lower()
    return mapping


def extract_groups(claims: Dict[str, Any]) -> List[str]:
    groups = claims.get("groups") or claims.get("roles") or []
    if isinstance(groups, str):
        return [groups.lower()]
    return [str(g).lower() for g in groups]


def map_claims_to_roles(claims: Dict[str, Any]) -> List[str]:
    """Map OIDC claims → governance role names (database RBAC)."""
    group_map = _load_group_map()
    matched: List[str] = []
    for group in extract_groups(claims):
        role = group_map.get(group)
        if role and role not in matched:
            matched.append(role)

    email = (claims.get("email") or claims.get("preferred_username") or "").lower()
    examiner_emails = {
        e.strip().lower()
        for e in os.environ.get("AI_GRADER_EXAMINER_EMAILS", "").split(",")
        if e.strip()
    }
    admin_emails = {
        e.strip().lower()
        for e in os.environ.get("AI_GRADER_ADMIN_EMAILS", "").split(",")
        if e.strip()
    }

    if email in admin_emails and "admin" not in matched:
        matched.append("admin")
    elif email in examiner_emails and "examiner" not in matched:
        matched.append("examiner")

    if not matched:
        matched.append("student")
    return matched


def claims_to_user_profile(claims: Dict[str, Any]) -> Dict[str, str]:
    sub = str(claims.get("sub") or claims.get("oid") or claims.get("id") or "")
    email = str(claims.get("email") or claims.get("preferred_username") or "")
    first = str(claims.get("given_name") or claims.get("name", "").split(" ")[0] or "")
    last = str(claims.get("family_name") or "")
    if not last and claims.get("name") and " " in str(claims["name"]):
        last = str(claims["name"]).split(" ", 1)[1]
    return {
        "sub": sub,
        "email": email,
        "first_name": first,
        "last_name": last,
    }
