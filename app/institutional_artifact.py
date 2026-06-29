"""
Signed institutional artifacts — facilitator verdicts as governance provenance.

Content-addressable (SHA-256) records for freeze transitions, RFC legitimacy,
and governance provenance. Not a mere form submission.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_VERSION = "signed_institutional_artifact_v1"
ARTIFACTS_DIR = Path("app/calibration/institutional_artifacts")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sign_institutional_artifact(
    body: Dict[str, Any],
    *,
    artifact_kind: str,
    signatory_name: str,
    signatory_role: str,
    institution_affirmation: bool,
    freeze_epoch_id: str = "",
    freeze_id: str = "",
    provenance_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a signed institutional artifact from workshop/RFC verdict body.
    """
    if not signatory_name.strip():
        raise ValueError("signatory_name required")
    if not institution_affirmation:
        raise ValueError("institution_affirmation must be true to sign artifact")

    content_hash = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    artifact_id = f"art_{content_hash[:16]}"

    artifact = {
        "artifact_type": "signed_institutional_artifact",
        "artifact_version": ARTIFACT_VERSION,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "content_hash": content_hash,
        "signed_at": _utc_now(),
        "signatory": {
            "name": signatory_name.strip(),
            "role": (signatory_role or "governance_facilitator").strip(),
            "institution_affirmation": True,
            "affirmation_ar": (
                "أؤكد أن هذا verdict مؤسسي — وليس رأياً شخصياً — "
                "ويُستخدم في freeze transition provenance."
            ),
        },
        "governance_context": {
            "freeze_epoch_id": freeze_epoch_id,
            "freeze_id": freeze_id,
        },
        "provenance_refs": list(provenance_refs or []),
        "artifact_body": body,
        "provenance_purpose_ar": (
            "جزء من governance provenance — freeze transitions · RFC legitimacy · epoch review"
        ),
    }

    _persist_artifact(artifact)
    return artifact


def _persist_artifact(artifact: Dict[str, Any]) -> Optional[str]:
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACTS_DIR / f"{artifact['artifact_id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, ensure_ascii=False, indent=2)
        index_path = ARTIFACTS_DIR / "artifacts_index.jsonl"
        with open(index_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "artifact_id": artifact["artifact_id"],
                        "artifact_kind": artifact["artifact_kind"],
                        "content_hash": artifact["content_hash"],
                        "signed_at": artifact["signed_at"],
                        "signatory": artifact["signatory"]["name"],
                        "freeze_epoch_id": (artifact.get("governance_context") or {}).get(
                            "freeze_epoch_id"
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return str(path)
    except OSError:
        return None


def load_artifact(artifact_id: str) -> Optional[Dict[str, Any]]:
    path = ARTIFACTS_DIR / f"{artifact_id}.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def verify_artifact_integrity(artifact: Dict[str, Any]) -> Dict[str, Any]:
    body = artifact.get("artifact_body") or {}
    expected = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    stored = artifact.get("content_hash", "")
    return {
        "artifact_id": artifact.get("artifact_id"),
        "integrity_ok": expected == stored,
        "content_hash": stored,
        "recomputed_hash": expected,
    }


def list_artifacts(
    *,
    freeze_epoch_id: Optional[str] = None,
    artifact_kind: Optional[str] = None,
) -> List[Dict[str, Any]]:
    index_path = ARTIFACTS_DIR / "artifacts_index.jsonl"
    if not index_path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(index_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if freeze_epoch_id and row.get("freeze_epoch_id") != freeze_epoch_id:
                    continue
                if artifact_kind and row.get("artifact_kind") != artifact_kind:
                    continue
                rows.append(row)
    except OSError:
        return []
    return rows

