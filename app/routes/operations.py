"""Operations API — dashboards, archival, backup policy."""
from __future__ import annotations

from fastapi import APIRouter

from app.ops.backup_policy import backup_policy
from app.ops.incident_response import IncidentState, advance_incident, create_incident, is_audit_frozen, run_incident_workflow
from app.ops.operational_metrics import operational_dashboard_snapshot
from app.ops.replay_archival import apply_archival_policy
from app.ops.sla import get_sla_definitions
from app.contracts.migration_policy import migration_policy_summary

router = APIRouter(prefix="/api/ops", tags=["operations"])


@router.get("/dashboard")
async def ops_dashboard_api():
    return operational_dashboard_snapshot()


@router.get("/backup-policy")
async def ops_backup_policy_api():
    return backup_policy()


@router.post("/archive/replay")
async def ops_replay_archive_api(dry_run: bool = True):
    return apply_archival_policy(dry_run=dry_run)


@router.get("/sla")
async def ops_sla_api():
    return get_sla_definitions()


@router.get("/migration-policy")
async def ops_migration_policy_api():
    return migration_policy_summary()


@router.get("/audit-freeze")
async def ops_audit_freeze_status_api():
    return {"audit_frozen": is_audit_frozen()}


@router.post("/incidents")
async def ops_create_incident_api(
    event_type: str,
    severity: str,
    description: str,
    trace_id: str = "",
    submission_key: str = "",
    session_id: str = "",
):
    if severity in ("critical", "high") and submission_key and session_id:
        return run_incident_workflow(
            event_type=event_type,
            severity=severity,
            description=description,
            trace_id=trace_id or None,
            submission_key=submission_key,
            session_id=session_id,
        )
    return create_incident(
        event_type=event_type,
        severity=severity,
        description=description,
        trace_id=trace_id or None,
        submission_key=submission_key or None,
        session_id=session_id or None,
    )


@router.post("/incidents/{incident_id}/resolve")
async def ops_resolve_incident_api(incident_id: str, note: str = "resolved"):
    return advance_incident(incident_id, IncidentState.RESOLVED, note=note)
