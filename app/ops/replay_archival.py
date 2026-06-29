"""Long-term replay archival — hot / warm / cold lifecycle."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ArchivalTier:
    name: str
    max_age_days: int
    action: str


DEFAULT_TIERS: tuple[ArchivalTier, ...] = (
    ArchivalTier("hot", int(os.environ.get("AI_GRADER_ARCHIVE_HOT_DAYS", "30")), "keep_local"),
    ArchivalTier("warm", int(os.environ.get("AI_GRADER_ARCHIVE_WARM_DAYS", "90")), "move_to_warm"),
    ArchivalTier("cold", int(os.environ.get("AI_GRADER_ARCHIVE_COLD_DAYS", "365")), "move_to_cold"),
    ArchivalTier("retention", int(os.environ.get("AI_GRADER_ARCHIVE_RETENTION_DAYS", "1095")), "manual_review"),
)


def _age_days(path: Path) -> float:
    mtime = path.stat().st_mtime
    return (datetime.now(timezone.utc).timestamp() - mtime) / 86400.0


def classify_snapshot(path: Path) -> str:
    age = _age_days(path)
    tier = "hot"
    for t in DEFAULT_TIERS:
        if age <= t.max_age_days:
            return tier
        tier = t.name
    return "retention"


def apply_archival_policy(
    *,
    dry_run: bool = True,
    source_root: Path | str = "uploads/replay_snapshots",
) -> Dict[str, Any]:
    """
    Evaluate replay snapshots against lifecycle policy.

    warm → uploads/archive/warm/
    cold → uploads/archive/cold/ (or S3 when object store enabled)
    """
    root = Path(source_root)
    warm_root = Path("uploads/archive/warm/replay_snapshots")
    cold_root = Path("uploads/archive/cold/replay_snapshots")
    actions: List[Dict[str, Any]] = []

    if not root.is_dir():
        return {"status": "ok", "actions": [], "note": "no snapshots"}

    for snap in root.rglob("deterministic_hash.json"):
        session_dir = snap.parent
        tier = classify_snapshot(session_dir)
        rel = session_dir.relative_to(root)
        action: Dict[str, Any] = {"path": str(session_dir), "tier": tier, "age_days": round(_age_days(session_dir), 1)}

        if tier == "warm":
            dest = warm_root / rel
            action["action"] = "move_to_warm"
            action["dest"] = str(dest)
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.move(str(session_dir), str(dest))
        elif tier in ("cold", "retention"):
            dest = cold_root / rel
            action["action"] = "move_to_cold" if tier == "cold" else "manual_retention_review"
            action["dest"] = str(dest)
            if not dry_run and tier == "cold":
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.move(str(session_dir), str(dest))
        else:
            action["action"] = "keep_hot"

        actions.append(action)

    manifest_path = Path("uploads/ops/archival_last_run.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"dry_run": dry_run, "actions": actions}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"status": "ok", "dry_run": dry_run, "count": len(actions), "actions": actions}
