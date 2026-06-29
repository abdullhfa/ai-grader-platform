"""Unified secret loader — Vault → K8s secrets → env."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from app.security.vault_provider import load_from_vault


@lru_cache(maxsize=128)
def get_secret(key: str, *, default: Optional[str] = None) -> Optional[str]:
    """
    Resolve secret with precedence:
    1. Vault (when configured)
    2. Environment variable
    3. default
    """
    vault_val = load_from_vault(key)
    if vault_val:
        return vault_val
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    return default


def hydrate_env_from_vault(prefix: str = "AI_GRADER_") -> int:
    """Load Vault secrets into os.environ for legacy code paths."""
    if not os.environ.get("AI_GRADER_VAULT_ADDR"):
        return 0
    count = 0
    for key in (
        "DATABASE_URL",
        "AI_GRADER_S3_SECRET_KEY",
        "AI_GRADER_AZURE_CLIENT_SECRET",
        "GOOGLE_CLIENT_SECRET",
        "AI_GRADER_OIDC_CLIENT_SECRET",
        "AI_GRADER_REDIS_URL",
        "AI_GRADER_RABBITMQ_URL",
    ):
        if os.environ.get(key):
            continue
        val = load_from_vault(key)
        if val:
            os.environ[key] = val
            count += 1
    return count
