"""Secret loading policy — env fallback with validation."""
from __future__ import annotations

import os
from typing import FrozenSet

REQUIRED_PRODUCTION_SECRETS: FrozenSet[str] = frozenset({
    "DATABASE_URL",
})

SENSITIVE_KEYS: FrozenSet[str] = frozenset({
    "DATABASE_URL",
    "AI_GRADER_S3_SECRET_KEY",
    "AI_GRADER_AZURE_CLIENT_SECRET",
    "GOOGLE_CLIENT_SECRET",
    "AI_GRADER_OIDC_CLIENT_SECRET",
    "AI_GRADER_VAULT_TOKEN",
    "SECRET_KEY",
})


def validate_secret_policy(*, environment: str | None = None) -> dict:
    env = (environment or os.environ.get("AI_GRADER_ENV", "production")).lower()
    missing = [k for k in REQUIRED_PRODUCTION_SECRETS if not os.environ.get(k)]
    warnings = []
    if env == "production":
        for key in SENSITIVE_KEYS:
            val = os.environ.get(key, "")
            if val and len(val) < 16 and key != "SECRET_KEY":
                warnings.append(f"{key}_weak_length")
    return {
        "environment": env,
        "ok": len(missing) == 0 or env != "production",
        "missing_required": missing,
        "warnings": warnings,
        "policy": "secret_policy_v1",
    }
