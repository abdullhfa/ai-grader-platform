"""Frozen schema version constants — do not change without major bump."""
from __future__ import annotations

REPLAY_SCHEMA_VERSION = "1.0"
REASONING_SCHEMA_VERSION = "1.0"
AUDIT_SCHEMA_VERSION = "1.0"
EVIDENCE_SCHEMA_VERSION = "1.0"
GAMEPLAY_SCHEMA_VERSION = "1.0"
GOVERNANCE_SCHEMA_VERSION = "1.0"
PLATFORM_VERSION = "1.0.0-institutional"

SCHEMA_VERSIONS = {
    "replay_schema_version": REPLAY_SCHEMA_VERSION,
    "reasoning_schema_version": REASONING_SCHEMA_VERSION,
    "audit_schema_version": AUDIT_SCHEMA_VERSION,
    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "gameplay_schema_version": GAMEPLAY_SCHEMA_VERSION,
    "governance_schema_version": GOVERNANCE_SCHEMA_VERSION,
    "platform_version": PLATFORM_VERSION,
}
