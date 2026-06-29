"""Platform contract freeze — schema versions and API stability."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

PLATFORM_VERSION = "1.0.0-institutional"
CONTRACT_FREEZE_STATUS = "frozen"


@lru_cache(maxsize=1)
def load_contract_manifest() -> Dict[str, Any]:
    path = SCHEMAS_DIR / "CONTRACT_MANIFEST.json"
    if not path.is_file():
        return {"schema": "platform_contract_manifest_v1", "status": "missing", "contracts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_api_contracts() -> Dict[str, Any]:
    path = SCHEMAS_DIR / "api_contracts_v1.json"
    if not path.is_file():
        return {"schema": "api_contracts_v1", "endpoints": []}
    return json.loads(path.read_text(encoding="utf-8"))


def get_frozen_contract(name: str) -> Dict[str, Any]:
    manifest = load_contract_manifest()
    contracts = manifest.get("contracts") or {}
    if name not in contracts:
        raise KeyError(f"unknown frozen contract: {name}")
    return dict(contracts[name])


def validate_platform_contracts() -> Dict[str, Any]:
    """Verify all referenced schema files exist on disk."""
    manifest = load_contract_manifest()
    missing: List[str] = []
    for name, spec in (manifest.get("contracts") or {}).items():
        schema_file = spec.get("schema_file")
        if schema_file and not (SCHEMAS_DIR / schema_file).is_file():
            missing.append(f"{name}:{schema_file}")
    api_path = SCHEMAS_DIR / "api_contracts_v1.json"
    return {
        "platform_version": PLATFORM_VERSION,
        "freeze_status": manifest.get("status", CONTRACT_FREEZE_STATUS),
        "ok": len(missing) == 0 and api_path.is_file(),
        "missing_schemas": missing,
        "contract_count": len(manifest.get("contracts") or {}),
        "api_endpoint_count": len(load_api_contracts().get("endpoints") or []),
    }


def build_freeze_report() -> Dict[str, Any]:
    from app.contracts.schema_versions import SCHEMA_VERSIONS

    return {
        "platform_version": PLATFORM_VERSION,
        "schema_versions": SCHEMA_VERSIONS,
        "manifest": load_contract_manifest(),
        "api_contracts": load_api_contracts(),
        "validation": validate_platform_contracts(),
        "policy": "no_breaking_changes_without_major_version_bump",
    }
