# Incident Recovery Runbook

## Severity levels

| Level | Example | Response |
|-------|---------|----------|
| S1 | Replay tampering detected | Stop signoffs, preserve audit logs |
| S2 | Malware scan bypass | Quarantine uploads, rotate secrets |
| S3 | Queue backlog | Scale workers (HPA) |
| S4 | SSO outage | Fallback to local auth (dev only) |

## Replay integrity incident

1. `GET /api/security/tamper/replay/{submission_key}/{session_id}`
2. If `integrity: tampered` → block appeals/signoffs for session
3. Preserve `uploads/governance/audit/` and `uploads/security/security_audit.jsonl`
4. Re-export from last known-good archive: `uploads/archive/warm/`

## PostgreSQL recovery

1. Restore latest WAL backup to staging
2. Run `python -m app.database` (init_db + RBAC seed)
3. Verify `GET /api/contracts/validate`

## Queue recovery

1. Inspect `uploads/audit/dead_letter.jsonl`
2. Re-queue failed tasks manually via Celery
3. Monitor `GET /api/ops/dashboard` → queue latency metrics

## Malware false positive

1. Review quarantine: `uploads/quarantine/{quarantine_id}/manifest.json`
2. If false positive → update blocklist exclusion
3. Re-release via `POST /api/security/scan`

## Correlation tracing

Every incident should capture:

- `trace_id` (response header `X-Trace-Id`)
- `submission_id`, `replay_id`, `session_id`
- Security audit: `GET /api/security/audit`

## Escalation

- Governance override disputes → Senior Examiner + replay bundle export
- Security incidents → preserve tamper hashes before any remediation
