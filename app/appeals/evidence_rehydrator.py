"""Rehydrate appeal evidence from replay snapshot only — no re-run."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.governance.replay_viewer import load_replay_inspection_bundle


def rehydrate_appeal_evidence(submission_key: str, session_id: str) -> Dict[str, Any]:
    """
    Appeals depend on frozen replay snapshot — never re-execute student project.
    """
    base = Path("uploads/replay_snapshots") / submission_key / session_id
    if not base.is_dir():
        return {"status": "not_found", "error": "replay_snapshot_missing"}

    bundle = load_replay_inspection_bundle(submission_key, session_id)
    if not bundle.deterministic_hash:
        return {"status": "not_found", "error": "replay_snapshot_incomplete"}

    return {
        "status": "ok",
        "source": "replay_snapshot_only",
        "rehydration_policy": "no_runtime_reexecution",
        "deterministic_hash": bundle.deterministic_hash,
        "bundle": bundle.to_dict(),
    }
