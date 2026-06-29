"""Security API — policy, audit, tamper verification, scanning."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.security.rotation import rotation_status
from app.security.scanning.pipeline import scan_submission_path, scanning_enabled
from app.security.secret_policy import validate_secret_policy
from app.security.security_audit import read_security_audit
from app.security.tamper import verify_audit_log_integrity, verify_replay_integrity
from app.ops.correlation import get_correlation

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/policy")
async def security_policy_api():
    from app.security.vault_provider import kubernetes_secrets_mode, vault_enabled

    return {
        "secret_policy": validate_secret_policy(),
        "vault_enabled": vault_enabled(),
        "kubernetes_secrets": kubernetes_secrets_mode(),
        "malware_scanning": scanning_enabled(),
    }


@router.get("/audit")
async def security_audit_api(limit: int = 100):
    return {"events": read_security_audit(limit=limit)}


@router.get("/rotation")
async def security_rotation_api():
    return rotation_status()


@router.get("/tamper/replay/{submission_key}/{session_id}")
async def tamper_replay_api(submission_key: str, session_id: str):
    snap = Path("uploads/replay_snapshots") / submission_key / session_id
    result = verify_replay_integrity(snap)
    if result.get("error") == "missing_deterministic_hash":
        raise HTTPException(status_code=404, detail="Replay snapshot not found")
    return result


@router.get("/tamper/audit/{session_id}")
async def tamper_audit_api(session_id: str):
    log_path = Path("uploads/governance/audit") / session_id.replace("/", "_") / "audit_log.jsonl"
    return verify_audit_log_integrity(log_path)


@router.post("/scan")
async def security_scan_api(request: Request, path: str, submission_key: str = ""):
    ctx = get_correlation()
    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    result = scan_submission_path(target, submission_key=submission_key)

    from app.security.security_audit import log_security_action

    actor = request.client.host if request.client else "api"
    log_security_action(
        action="malware_scan",
        actor=actor,
        resource=str(target),
        outcome=result.get("status", "unknown"),
        trace_id=ctx.trace_id if ctx else None,
        ip_address=actor,
        metadata={"quarantine_id": result.get("quarantine_id")},
    )
    return result
