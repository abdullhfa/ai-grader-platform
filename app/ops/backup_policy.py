"""Backup and disaster recovery policy — operational contract."""
from __future__ import annotations

import os
from typing import Any, Dict


def backup_policy() -> Dict[str, Any]:
    return {
        "schema": "backup_policy_v1",
        "postgresql": {
            "strategy": "WAL_continuous_archiving",
            "enabled": "postgresql" in os.environ.get("DATABASE_URL", "").lower(),
            "note": "Enable pg_basebackup + WAL shipping in production",
        },
        "object_store": {
            "strategy": "versioned_buckets",
            "backend": os.environ.get("AI_GRADER_OBJECT_STORE", "local"),
            "bucket": os.environ.get("AI_GRADER_S3_BUCKET", "ai-grader"),
        },
        "replay_snapshots": {
            "strategy": "immutable_archive",
            "path": "uploads/replay_snapshots",
            "lifecycle": "see app.ops.replay_archival",
        },
        "audit_logs": {
            "strategy": "append_only_replication",
            "paths": [
                "uploads/governance/audit",
                "uploads/appeals/audit",
                "uploads/audit",
            ],
        },
        "redis": {
            "strategy": "AOF_persistence",
            "note": "Redis is cache/queue — rebuild from PostgreSQL + replay archive",
        },
    }
