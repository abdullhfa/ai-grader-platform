"""Submission safety checks — path traversal, suspicious archives, oversized payloads."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_SUBMISSION_BYTES = int(os.environ.get("AI_GRADER_MAX_SUBMISSION_BYTES", str(500 * 1024 * 1024)))
MAX_ARCHIVE_ENTRIES = int(os.environ.get("AI_GRADER_MAX_ARCHIVE_ENTRIES", "5000"))
MAX_PATH_DEPTH = int(os.environ.get("AI_GRADER_MAX_PATH_DEPTH", "12"))

SUSPICIOUS_EXTENSIONS = frozenset({
    ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar", ".dll", ".scr", ".msi", ".reg",
})
SUSPICIOUS_NAMES = frozenset({
    "autorun.inf", "desktop.ini", "launch.bat", "install.exe",
})


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def is_path_traversal(path: str) -> bool:
    normalized = _normalize_rel(path)
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return True
    if normalized.startswith("\\\\") or normalized.startswith("//"):
        return True
    return False


def is_suspicious_entry(name: str) -> bool:
    base = Path(name).name.lower()
    if base in SUSPICIOUS_NAMES:
        return True
    return Path(base).suffix.lower() in SUSPICIOUS_EXTENSIONS


def validate_submission_paths(paths: List[str]) -> Dict[str, Any]:
    """Reject malicious or malformed submission paths before runtime."""
    issues: List[str] = []
    for raw in paths:
        if not raw or not raw.strip():
            issues.append("empty_path")
            continue
        if is_path_traversal(raw):
            issues.append(f"path_traversal:{raw}")
        depth = len(_normalize_rel(raw).split("/"))
        if depth > MAX_PATH_DEPTH:
            issues.append(f"path_depth_exceeded:{raw}")
        if is_suspicious_entry(raw):
            issues.append(f"suspicious_entry:{raw}")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "policy": "submission_guard_v1",
    }


def validate_file_size(path: Path, *, max_bytes: Optional[int] = None) -> Dict[str, Any]:
    limit = max_bytes or MAX_SUBMISSION_BYTES
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if size > limit:
        return {"ok": False, "error": "file_too_large", "bytes": size, "limit": limit}
    return {"ok": True, "bytes": size}
