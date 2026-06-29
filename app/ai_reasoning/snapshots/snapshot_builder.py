"""Replay snapshot builder for audit-grade grading."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from app.ai_reasoning.snapshots.deterministic_hash import compute_snapshot_hash
from app.contracts.schema_versions import SCHEMA_VERSIONS


def build_reasoning_snapshot(
    *,
    submission_key: str,
    session_id: Optional[str],
    grading_result: Dict[str, Any],
    reasoning_session: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = Path("uploads/replay_snapshots") / submission_key
    if session_id:
        base = base / session_id
    base.mkdir(parents=True, exist_ok=True)

    sections = {
        "runtime": artifact_inventory.get("runtime_observation_report") if artifact_inventory else {},
        "gameplay": grading_result.get("gameplay_analysis") or {},
        "timeline": (grading_result.get("gameplay_analysis") or {}).get("timeline"),
        "evidence": reasoning_session.get("criterion_graphs"),
        "ai_reasoning": reasoning_session,
        "grading_summary": {
            "grade_level": grading_result.get("grade_level"),
            "percentage": grading_result.get("percentage"),
            "criteria_results": grading_result.get("criteria_results"),
        },
    }

    for name, payload in sections.items():
        target = base / name
        target.mkdir(parents=True, exist_ok=True)
        out = target / f"{name}.json"
        out.write_text(json.dumps(payload or {}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Link runtime session artifacts if present
    if session_id:
        session_root = Path("uploads/runtime_sessions") / submission_key / session_id
        shots_src = session_root / "screenshots"
        shots_dst = base / "screenshots"
        if shots_src.is_dir():
            shots_dst.mkdir(parents=True, exist_ok=True)
            for fp in shots_src.glob("*.png"):
                try:
                    shutil.copy2(fp, shots_dst / fp.name)
                except OSError:
                    pass

    manifest = {
        "submission_key": submission_key,
        "session_id": session_id,
        "snapshot_root": str(base),
        "sections": list(sections.keys()),
        **SCHEMA_VERSIONS,
        "truth_anchor": "replay_snapshot_canonical",
    }
    digest = compute_snapshot_hash(sections)
    manifest["deterministic_hash"] = digest
    (base / "deterministic_hash.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
