"""HashiCorp Vault provider — optional institutional secrets backend."""
from __future__ import annotations

import os
from typing import Optional


def vault_enabled() -> bool:
    return bool(os.environ.get("AI_GRADER_VAULT_ADDR", "").strip())


def load_from_vault(key: str) -> Optional[str]:
    if not vault_enabled():
        return None
    addr = os.environ["AI_GRADER_VAULT_ADDR"].rstrip("/")
    token = os.environ.get("AI_GRADER_VAULT_TOKEN", "")
    mount = os.environ.get("AI_GRADER_VAULT_MOUNT", "secret")
    path = os.environ.get("AI_GRADER_VAULT_PATH", "ai-grader")
    if not token:
        return None
    try:
        import httpx

        url = f"{addr}/v1/{mount}/data/{path}"
        resp = httpx.get(url, headers={"X-Vault-Token": token}, timeout=5.0)
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {}).get("data") or {}
        return data.get(key) or data.get(key.lower())
    except Exception:
        return None


def kubernetes_secrets_mode() -> bool:
    return os.environ.get("AI_GRADER_SECRETS_BACKEND", "").lower() in (
        "kubernetes",
        "k8s",
    )
