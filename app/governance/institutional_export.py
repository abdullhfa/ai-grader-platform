"""Institutional export — signed reports, evidence JSON, replay ZIP."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.governance.replay_viewer import load_replay_inspection_bundle


def export_evidence_json(submission_key: str, session_id: str) -> Dict[str, Any]:
    bundle = load_replay_inspection_bundle(submission_key, session_id)
    return {
        "format": "json",
        "schema": "institutional_evidence_export_v1",
        "bundle": bundle.to_dict(),
    }


def build_replay_package_zip(submission_key: str, session_id: str) -> bytes:
    """Zip replay snapshot for appeals archival."""
    base = Path("uploads/replay_snapshots") / submission_key / session_id
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if base.is_dir():
            for fp in base.rglob("*"):
                if fp.is_file():
                    arcname = str(fp.relative_to(base))
                    zf.write(fp, arcname=arcname)
        else:
            zf.writestr(
                "missing.txt",
                "Replay snapshot not found — appeals require frozen replay package",
            )
    return buf.getvalue()


def export_signed_report_stub(
    submission_key: str,
    session_id: str,
    *,
    signed_evaluation_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """JSON signed report stub — PDF generation can wrap this later."""
    bundle = load_replay_inspection_bundle(submission_key, session_id)
    signoff_path = (
        Path("uploads/governance/signoffs")
        / submission_key.replace("/", "_")
        / f"{session_id}.json"
    )
    signoff = None
    if signoff_path.is_file():
        try:
            signoff = json.loads(signoff_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "format": "signed_report_json",
        "schema": "institutional_signed_report_v1",
        "submission_key": submission_key,
        "session_id": session_id,
        "replay_hash": bundle.deterministic_hash,
        "signed_evaluation_hash": signed_evaluation_hash or (signoff or {}).get("signed_evaluation_hash"),
        "signoff": signoff,
        "grading_summary": bundle.grading_summary,
        "audit_note": "Replay-first institutional record — not LLM summary alone",
    }
