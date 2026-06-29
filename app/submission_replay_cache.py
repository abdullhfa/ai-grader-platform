"""Global generation counter — invalidates batch submission replay after admin cache clear."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path("uploads/config/submission_replay_cache_generation.json")


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"generation": 0, "cleared_at": None}
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"generation": 0, "cleared_at": None}


def _save_config(data: dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def current_replay_cache_generation() -> int:
    return int(_load_config().get("generation") or 0)


def bump_replay_cache_generation() -> int:
    cfg = _load_config()
    new_gen = int(cfg.get("generation") or 0) + 1
    cfg["generation"] = new_gen
    cfg["cleared_at"] = datetime.now(timezone.utc).isoformat()
    _save_config(cfg)
    return new_gen


def submission_replay_generation(submission: Any) -> int:
    """Generation stamped on submission when graded; 0 = legacy / pre-stamp."""
    raw = getattr(submission, "grading_snapshot_json", None)
    if not raw:
        return 0
    try:
        snap = json.loads(str(raw))
        gov = snap.get("grading_governance") if isinstance(snap, dict) else None
        if isinstance(gov, dict) and gov.get("replay_cache_generation") is not None:
            return int(gov["replay_cache_generation"])
    except Exception:
        pass
    return 0


def submission_replay_cache_valid(submission: Any) -> bool:
    """False after admin cleared grading cache since this submission was graded."""
    return submission_replay_generation(submission) >= current_replay_cache_generation()
