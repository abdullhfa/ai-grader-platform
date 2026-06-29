"""Malware scanning pipeline — quarantine → scan → release or reject."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.security.scanning.clamav_scan import scan_with_clamav
from app.security.scanning.quarantine import mark_quarantine_failed, move_to_quarantine, release_from_quarantine
from app.security.scanning.reputation import check_hash_reputation
from app.security.scanning.yara_rules import scan_file_patterns


def scan_submission_path(
    path: Path,
    *,
    submission_key: str = "",
    release_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Full pipeline: quarantine → reputation → yara → clamav → release/reject.
    """
    if not path.exists():
        return {"status": "error", "error": "path_not_found"}

    qmeta = move_to_quarantine(path, submission_key=submission_key)
    qid = qmeta["quarantine_id"]
    qroot = Path("uploads/quarantine") / qid

    scan_targets: List[Path] = []
    if path.is_file():
        scan_targets = [qroot / path.name]
    else:
        payload = qroot / "payload"
        scan_targets = [p for p in payload.rglob("*") if p.is_file()][:50] if payload.is_dir() else []

    results: List[Dict[str, Any]] = []
    clean = True
    for target in scan_targets:
        if target.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            continue
        rep = check_hash_reputation(target)
        yara = scan_file_patterns(target)
        clam = scan_with_clamav(target)
        results.extend([rep, yara, clam])
        if rep.get("flagged") or yara.get("flagged") or clam.get("infected"):
            clean = False
            break
        if clam.get("clean") is False and not clam.get("skipped"):
            clean = False
            break

    if not clean:
        mark_quarantine_failed(qid, reason="malware_or_suspicious_pattern_detected")
        return {
            "status": "rejected",
            "quarantine_id": qid,
            "scan_results": results,
            "policy": "scan_before_runtime_v1",
        }

    released = None
    if release_dir:
        released = release_from_quarantine(qid, release_to=release_dir)

    return {
        "status": "clean",
        "quarantine_id": qid,
        "scan_results": results,
        "released": released,
        "policy": "scan_before_runtime_v1",
    }


def scanning_enabled() -> bool:
    return os.environ.get("AI_GRADER_MALWARE_SCAN", "1").strip().lower() in ("1", "true", "yes", "on")
