"""Tamper verification — replay, PDF, audit integrity hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.ai_reasoning.snapshots.deterministic_hash import compute_snapshot_hash


def compute_tamper_verification_hash(
    *,
    artifact_type: str,
    payload: Any,
    replay_hash: Optional[str] = None,
    signed_hash: Optional[str] = None,
) -> str:
    envelope = {
        "schema": "tamper_verification_v1",
        "artifact_type": artifact_type,
        "replay_hash": replay_hash,
        "signed_evaluation_hash": signed_hash,
        "content_hash": compute_snapshot_hash(payload),
    }
    return compute_snapshot_hash(envelope)


def verify_replay_integrity(snapshot_dir: Path) -> Dict[str, Any]:
    manifest_path = snapshot_dir / "deterministic_hash.json"
    if not manifest_path.is_file():
        return {"ok": False, "error": "missing_deterministic_hash"}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": str(exc)}

    stored = manifest.get("deterministic_hash")
    sections = {}
    for sub in snapshot_dir.iterdir():
        if sub.is_dir():
            jf = sub / f"{sub.name}.json"
            if jf.is_file():
                try:
                    sections[sub.name] = json.loads(jf.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    sections[sub.name] = {}

    recomputed = compute_snapshot_hash(sections)
    tamper_hash = compute_tamper_verification_hash(
        artifact_type="replay_snapshot",
        payload=sections,
        replay_hash=stored,
    )
    return {
        "ok": stored == recomputed,
        "stored_hash": stored,
        "recomputed_hash": recomputed,
        "tamper_verification_hash": tamper_hash,
        "integrity": "verified" if stored == recomputed else "tampered",
    }


def verify_audit_log_integrity(log_path: Path) -> Dict[str, Any]:
    if not log_path.is_file():
        return {"ok": False, "error": "missing_log"}
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"_corrupt": line[:80]})
    tamper_hash = compute_tamper_verification_hash(
        artifact_type="audit_log",
        payload=events,
    )
    corrupt = sum(1 for e in events if "_corrupt" in e)
    return {
        "ok": corrupt == 0,
        "event_count": len(events),
        "corrupt_lines": corrupt,
        "tamper_verification_hash": tamper_hash,
    }
