# Canary Rollout Runbook

**Prerequisite:** Staging validation passed (`STAGING_VALIDATION.md`).  
**Scope:** Controlled institutional rollout — not a feature release.

**Rollout policy:** Stability > Features — freeze contracts; validate only.

## Rollout path

```
staging pass → external pentest → canary (5–10 instructors) → institution-wide
```

## Recommended cohort

| Parameter | Value |
|-----------|-------|
| Instructors | 5–10 trusted pilot cohort |
| Environment | Sandboxed (isolated course / pilot org) |
| Duration | 2–4 weeks minimum |
| Replay retention | Enabled (do not purge during pilot) |
| Tracing | Verbose ON for full canary window |

## Strict observability (enable during canary)

| System | Setting |
|--------|---------|
| Loki | verbose log retention; retain governance + security streams |
| Tempo | ON — trace every submission → replay → signoff path |
| Prometheus | scrape `/api/metrics`; alert on replay mismatch + dead letters |
| Grafana | dashboard pinned: queue depth, SLA, integrity |
| Replay retention | max — no purge during pilot |
| Audit freeze | enabled via incident workflow (`POST /api/ops/incidents`) |

Stack includes Loki + Tempo + Prometheus via `docker-compose.ops.yml`. Ensure OTEL export is active:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318
```

## Enable before canary

```env
AI_GRADER_ENV=production
AI_GRADER_CELERY_ENABLED=1
AI_GRADER_ASYNC_MALWARE_SCAN=1
AI_GRADER_ASYNC_REASONING=1
AI_GRADER_OBJECT_STORE=s3
AI_GRADER_STRICT_EVIDENCE_GATE=1
```

## Monitor continuously

| Signal | Source | Alert threshold |
|--------|--------|-------------------|
| Queue depth | `/api/ops/dashboard` | Sustained backlog > 50 jobs |
| Runtime SLA | `/api/ops/sla` | p95 > configured target |
| Tamper events | `uploads/security/security_audit.jsonl` | Any `tampered` on production snapshots |
| Dead letter | `uploads/audit/dead_letter.jsonl` | Any new entry |
| Appeal volume | governance audit log | Spike > 3× baseline |

## Success KPIs (canary pass criteria)

| Indicator | Target | Dashboard field |
|-----------|--------|-----------------|
| Runtime success rate | **>95%** | derive from `runtime_failures` vs total jobs |
| Replay restore success | **100%** | tamper API + archival restore drills |
| False governance escalations | low | manual review of examiner overrides |
| Hallucination rejects | stable | `hallucination_manual_review` — no spike |
| Appeal reversal rate | low | appeals audit vs signoff count |
| Queue dead letters | **~0** | `uploads/audit/dead_letter.jsonl` |
| Replay hash mismatch | **0** | `metrics.replay_mismatch` |

After all KPIs hold for the full canary window (2–4 weeks), the platform is **institution-wide deployable**.

## Pentest focus (before / during canary)

| Area | Severity |
|------|----------|
| Sandbox escape | critical |
| Replay tampering | critical |
| RBAC bypass | critical |
| Fake signoff hashes | critical |
| Poisoned gameplay uploads | high |

Full scope: `PENTEST_CHECKLIST.md` (P-01 → P-15).

## Go / no-go checklist

- [ ] External pentest: no unmitigated critical findings
- [ ] Contract freeze acknowledged (`CONTRACT_FREEZE.md`)
- [ ] Incident response on-call defined (`INCIDENT_RECOVERY.md`)
- [ ] Backup + replay archival verified
- [ ] RBAC roles assigned (examiner vs instructor vs student)
- [ ] Canary instructors trained on governance UI

## Rollback triggers

- Replay integrity failure on production snapshots
- RBAC bypass confirmed
- Unbounded queue growth or worker crash loop
- Data loss in object store or audit trail

## Rollback procedure

1. Freeze new submissions (maintenance mode or ingress block)
2. `POST /api/ops/incidents` — audit freeze + replay preservation
3. Preserve logs, traces, and snapshot hashes
4. Roll back to last known-good deployment tag
5. Post-incident review before re-enabling canary

## Deferred until after canary

| Item | When |
|------|------|
| WORM / immutable storage | University or compliance mandate |
| Enterprise SAML | Institutional IdP requirement (OIDC sufficient for pilot) |
