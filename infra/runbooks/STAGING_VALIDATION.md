# Staging Validation Runbook

**Master plan:** `GO_LIVE_EXECUTION.md` (Phases 1–6)

**Goal:** Controlled deployment validation before external pentest or canary rollout.  
**Contract version:** 1.0.0-institutional (frozen)  
**Truth anchor:** Replay Snapshot = canonical truth (institutional policy anchor)

**Rollout policy:** Stability > Features — do not change frozen contracts during staging, pentest, or canary.

**Discipline:** execute → validate → observe → harden

## Preflight (local, before deploy)

```bash
python tools/go_live_preflight.py
```

Runs contract freeze check, chaos/pentest regression, and Docker availability.

## Staging observability (enable at go-live)

| System | Setting |
|--------|---------|
| Loki | verbose (`-log.level=debug` in staging compose) |
| Tempo | full tracing (`OTEL_TRACES_SAMPLER=always_on`) |
| Prometheus | alerts enabled (`infra/prometheus/alerts.yml`) |
| Replay retention | max (`AI_GRADER_ARCHIVE_RETENTION_DAYS=3650`) |
| Governance audit | strict (`AI_GRADER_STRICT_EVIDENCE_GATE=1`) |

## Bring up staging stack

```bash
python tools/deploy_staging.py
# or on Linux/CI:
bash tools/deploy_staging.sh
```

Manual equivalent:

```bash
cd infra/docker
docker compose \
  -f docker-compose.yml \
  -f docker-compose.ops.yml \
  -f docker-compose.staging.yml \
  up --build -d
python ../../tools/staging_smoke.py --base-url http://localhost:8000
```

Deploy record written to `uploads/ops/last_staging_deploy.json`.

## External pentest

Hand off `infra/pentest/` to the external team (`PENTEST_PACK.md` + `REPORT_TEMPLATE.md`).

## 1. Replay consistency (primary focus)

Monitor via `GET /api/ops/dashboard` and tamper endpoints:

| Metric | Target | Source |
|--------|--------|--------|
| `replay_hash` mismatch | **0** | `metrics.replay_mismatch`, tamper API |
| Evidence drift | **0** | evidence graph hash vs snapshot |
| Schema violations | **0** | `GET /api/contracts/validate` |
| Reasoning divergence | minimal | compare reasoning runs on same frozen snapshot |

Daily check during staging:

```bash
curl -s http://localhost:8000/api/ops/dashboard | jq '.metrics.replay_mismatch'
curl -s http://localhost:8000/api/contracts/validate | jq '.ok'
```

Any non-zero replay mismatch → **stop rollout**, preserve snapshot, open incident.

## 2. Queue stability

| Queue | Watch for | Action if degraded |
|-------|-----------|-------------------|
| `runtime_jobs` | latency p95 | scale `worker-runtime`; check sandbox timeouts |
| `gameplay_jobs` | memory / OOM | limit concurrent CV workers; check video size guards |
| `reasoning_jobs` | retries / backlog | scale `worker-reasoning`; verify async reasoning flag |
| `malware_jobs` | scan timeout | verify ClamAV health; check quarantine queue depth |
| `cv_jobs` | dead letters | inspect `uploads/audit/dead_letter.jsonl` |

## 3. Governance flow integrity

End-to-end path (no audit loss, hash drift, or evidence mismatch):

```
review → override → signoff → appeal → replay restore
```

| Step | Verify |
|------|--------|
| Review | Examiner UI loads replay timeline + evidence graph |
| Override | Audit event written; original snapshot preserved |
| Signoff | `signed_evaluation_hash` matches tamper verification |
| Appeal | Snapshot-only; **no** runtime re-execution |
| Replay restore | tamper API → `integrity: verified` |

## Validation matrix

| Domain | Required | How to verify |
|--------|----------|---------------|
| Real uploads | Yes | Submit assignment via grading API or UI; artifact lands in object store |
| Replay lifecycle | Yes | `uploads/replay_snapshots/{key}/{session}/deterministic_hash.json` created |
| Governance flow | Yes | `/governance/examiner` loads timeline + evidence graph |
| Appeal workflow | Yes | `POST /api/appeals` uses snapshot only; no runtime re-execution |
| RBAC / SSO | Yes | OIDC login; student blocked from examiner endpoints |
| Object-store archival | Yes | Replay artifacts visible in MinIO/S3; restore path works |
| Async queues | Yes | Celery workers consume `runtime_jobs`, `gameplay_jobs`, `cv_jobs`, `reasoning_jobs`, `malware_jobs` |
| Tracing | Yes | Responses include `X-Trace-Id`; Tempo/Loki receive spans/logs |

## Manual walkthrough (recommended order)

1. **Health** — `GET /api/health`, `GET /api/ready`, `GET /api/contracts/validate`
2. **Upload + grade** — one real submission end-to-end
3. **Replay integrity** — `GET /api/security/tamper/replay/{key}/{session}` → `integrity: verified`
4. **Governance** — examiner investigation, override note, signoff hash recorded
5. **Appeal** — open appeal against frozen snapshot; confirm no re-run
6. **Malware queue** — upload flagged file; quarantine + audit event logged
7. **Incident drill** — `POST /api/ops/incidents`; confirm audit freeze + replay preservation
8. **SLA dashboard** — `GET /api/ops/sla`, `GET /api/ops/dashboard`

## Pass criteria

- All smoke checks green
- At least one full submission → replay → governance → appeal path completed
- No contract validation failures (`/api/contracts/validate` → `ok: true`)
- Chaos regression suite passes locally before staging sign-off:

```bash
pytest tests/test_chaos_resilience.py tests/test_pentest_hardening.py -q
```

## Failures

| Symptom | First action |
|---------|--------------|
| Worker queue backlog | Check Redis/RabbitMQ; scale worker replicas |
| Replay hash mismatch | Stop rollout; preserve snapshot; run tamper investigation |
| SSO redirect loop | Verify OIDC callback URL and `AI_GRADER_SSO_*` env |
| Object store 403 | Check MinIO bucket policy and credentials |

## Next step after staging pass

1. External pentest (`PENTEST_CHECKLIST.md`)
2. Canary rollout (`CANARY_ROLLOUT.md`)
