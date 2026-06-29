"""Hash reputation — known malware SHA256 blocklist."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Set


def _blocklist_path() -> Path:
    return Path("uploads/security/malware_blocklist.json")


def _load_blocklist() -> Set[str]:
    path = _blocklist_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(h).lower() for h in (data.get("sha256") or [])}
    except (json.JSONDecodeError, OSError):
        return set()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_hash_reputation(path: Path) -> Dict[str, Any]:
    digest = file_sha256(path)
    blocklist = _load_blocklist()
    flagged = digest.lower() in blocklist
    return {
        "scanner": "hash_reputation",
        "sha256": digest,
        "flagged": flagged,
        "clean": not flagged,
    }
