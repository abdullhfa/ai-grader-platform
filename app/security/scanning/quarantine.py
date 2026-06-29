"""Submission quarantine — hold files until scan passes."""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def quarantine_path(quarantine_id: str) -> Path:
    return Path("uploads/quarantine") / quarantine_id


def move_to_quarantine(source: Path, *, submission_key: str = "") -> Dict[str, Any]:
    qid = f"q_{uuid.uuid4().hex[:12]}"
    dest = quarantine_path(qid)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / source.name
    if source.is_file():
        shutil.copy2(source, target)
    elif source.is_dir():
        shutil.copytree(source, dest / "payload", dirs_exist_ok=True)
        target = dest / "payload"

    meta = {
        "quarantine_id": qid,
        "source": str(source),
        "submission_key": submission_key,
        "status": "quarantined",
        "created_at": _utc_now(),
    }
    (dest / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def release_from_quarantine(quarantine_id: str, *, release_to: Path) -> Dict[str, Any]:
    src = quarantine_path(quarantine_id)
    if not src.is_dir():
        return {"ok": False, "error": "not_found"}
    release_to.mkdir(parents=True, exist_ok=True)
    payload = src / "payload"
    if payload.is_dir():
        shutil.copytree(payload, release_to / "payload", dirs_exist_ok=True)
    else:
        for fp in src.glob("*"):
            if fp.name != "manifest.json":
                shutil.copy2(fp, release_to / fp.name)
    manifest_path = src / "manifest.json"
    if manifest_path.is_file():
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        meta["status"] = "released"
        meta["released_at"] = _utc_now()
        (release_to / "quarantine_manifest.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return {"ok": True, "quarantine_id": quarantine_id, "release_to": str(release_to)}


def mark_quarantine_failed(quarantine_id: str, *, reason: str) -> None:
    src = quarantine_path(quarantine_id)
    manifest = src / "manifest.json"
    if manifest.is_file():
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        meta["status"] = "rejected"
        meta["reason"] = reason
        meta["rejected_at"] = _utc_now()
        manifest.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
