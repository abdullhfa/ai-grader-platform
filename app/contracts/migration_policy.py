"""Schema migration policy — version compatibility rules."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.contracts.schema_versions import SCHEMA_VERSIONS

SUPPORTED_REPLAY_VERSIONS = frozenset({"1.0"})
SUPPORTED_REASONING_VERSIONS = frozenset({"1.0"})
SUPPORTED_AUDIT_VERSIONS = frozenset({"1.0"})


def check_replay_compatibility(manifest: Dict[str, Any]) -> Dict[str, Any]:
    version = str(manifest.get("replay_schema_version") or manifest.get("schema_version") or "1.0")
    supported = version in SUPPORTED_REPLAY_VERSIONS
    return {
        "artifact": "replay_snapshot",
        "version": version,
        "supported": supported,
        "action": "read" if supported else "migrate_or_reject",
        "migration_policy": "major_version_bump_required_for_breaking_changes",
    }


def check_reasoning_compatibility(payload: Dict[str, Any]) -> Dict[str, Any]:
    version = str(payload.get("reasoning_schema_version") or "1.0")
    return {
        "artifact": "evidence_reasoning",
        "version": version,
        "supported": version in SUPPORTED_REASONING_VERSIONS,
        "action": "read" if version in SUPPORTED_REASONING_VERSIONS else "migrate_or_reject",
    }


def migrate_replay_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Add missing version fields to legacy snapshots (non-breaking)."""
    out = dict(manifest)
    if "replay_schema_version" not in out:
        out["replay_schema_version"] = SCHEMA_VERSIONS["replay_schema_version"]
    if "reasoning_schema_version" not in out:
        out["reasoning_schema_version"] = SCHEMA_VERSIONS["reasoning_schema_version"]
    if "audit_schema_version" not in out:
        out["audit_schema_version"] = SCHEMA_VERSIONS["audit_schema_version"]
    out["migration_applied"] = "legacy_version_stamp_v1"
    return out


def migration_policy_summary() -> Dict[str, Any]:
    return {
        "policy": "major_version_bump_required",
        "supported_replay_versions": sorted(SUPPORTED_REPLAY_VERSIONS),
        "supported_reasoning_versions": sorted(SUPPORTED_REASONING_VERSIONS),
        "supported_audit_versions": sorted(SUPPORTED_AUDIT_VERSIONS),
        "compatibility_guarantee": "v1_snapshots_readable_indefinitely",
        "current_versions": SCHEMA_VERSIONS,
    }
