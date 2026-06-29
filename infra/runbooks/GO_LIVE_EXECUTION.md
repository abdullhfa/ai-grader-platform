# Go-Live Execution Phase

**Status:** ACTIVE — execute → validate → observe → harden  
**Policy:** Stability > Innovation — **no contract or feature changes** during pentest/canary

**Truth anchor:** Replay Snapshot = canonical truth  
**Platform heartbeat:** `replay_hash mismatch = 0` → any deviation = incident + audit freeze

---

## Phase map

```
Phase 1  Deploy staging
Phase 2  Verify operational signals
Phase 3  External pentest
Phase 4  Fix critical findings only
Phase 5  Canary rollout (5–10 instructors)
Phase 6  Institution-wide rollout
```

---

## Phase 1 — Deploy Staging (NOW)

**Goal:** Full platform on real staging environment.

**Host:** Server or VM with Docker.

### Option A — deterministic (recommended)

```bash
python tools/deploy_staging.py --base-url http://localhost:8000
```

Runs: preflight → compose → health wait → smoke → deploy record.

### Option B — manual

```bash
python tools/go_live_preflight.py
```

Confirm:

- [ ] contracts frozen
- [ ] chaos tests passed
- [ ] pentest regression passed

Then:

```bash
cd infra/docker
docker compose \
  -f docker-compose.yml \
  -f docker-compose.ops.yml \
  -f docker-compose.staging.yml \
  up --build -d
```

```bash
python ../../tools/staging_smoke.py --base-url http://localhost:8000
```

**Deploy record:** `uploads/ops/last_staging_deploy.json`

**Pass:** smoke 6/6 · `/api/ready` 200 · deploy record written

See also: `STAGING_VALIDATION.md`

---

## Phase 2 — Verify Operational Signals

**Goal:** Confirm observability and platform heartbeat before pentest.

### Dashboards

| System | URL (default) |
|--------|---------------|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |
| Ops API | `GET /api/ops/dashboard` |

### Automated KPI check

```bash
python tools/verify_operational_signals.py --base-url http://localhost:8000
```

### Success KPIs

| KPI | Required |
|-----|----------|
| `replay_hash mismatch` | **0** |
| `replay restore` | **100%** |
| `dead letters` | **~0** |
| `runtime success` | **>95%** |
| `governance escalations` | **stable** |

Run one full path manually: upload → replay → governance → appeal → restore.

**Pass:** all KPIs green · traces visible in Tempo · governance logs in Loki

---

## Phase 3 — External Pentest

**Goal:** External confidence building — not random testing.

### Hand off to security team

```
infra/pentest/
```

| File | Purpose |
|------|---------|
| `PENTEST_PACK.md` | Scope, rules, endpoints, P-01→P-15 |
| `REPORT_TEMPLATE.md` | Required deliverable |
| `staging.env.example` | Sanitized env template |

### Priority tests

| Area | Severity |
|------|----------|
| Sandbox escape | critical |
| Replay tampering | critical |
| RBAC bypass | critical |
| Fake signoff hashes | critical |
| Poisoned uploads | high |

**During pentest:** contracts **frozen** — no schema or governance flow changes.

---

## Phase 4 — Fix Critical Findings Only

**Goal:** Remediate pentest findings without feature creep.

### Allowed

- Security fixes
- Operational fixes
- Replay integrity fixes

### Not allowed

- New features
- Contract changes
- Replay format changes
- Governance flow redesign
- New AI capabilities

Re-run after fixes:

```bash
pytest tests/test_pentest_hardening.py tests/test_chaos_resilience.py -q
python tools/staging_smoke.py --base-url http://localhost:8000
```

---

## Phase 5 — Canary Rollout

**Prerequisite:** Phase 1–4 complete.

**Cohort:** 5–10 trusted instructors · sandboxed course · 2–4 weeks

### Enable

- verbose tracing ON
- replay retention MAX
- governance audit STRICT
- anomaly alerts ON
- dead-letter monitoring ON

See: `CANARY_ROLLOUT.md`

### Monitor

| Signal | Watch |
|--------|-------|
| Appeal reversals | grading consistency |
| Replay determinism | stable |
| Evidence drift | zero |
| Dead-letter spikes | alerts |
| Runtime failures | trends |

**Pass:** canary KPIs hold full window · `replay_hash mismatch` remains 0

---

## Phase 6 — Institution-wide Rollout

**Prerequisite:** staging + pentest + canary all passed.

Gradual rollout by department/org unit. Maintain:

- deploy discipline (`deploy_staging.py` pattern for production)
- contract freeze
- incident workflow
- replay retention

---

## Do NOT do now

| Action | Reason |
|--------|--------|
| Redesign architecture | Stability > innovation |
| Modify contracts | Frozen until post-canary |
| Change replay format | Truth anchor integrity |
| Modify governance flow | Audit consistency |
| Add AI features | Rollout risk |

---

## Post-rollout (later only)

| Item | When |
|------|------|
| SAML | Large university IdP mandate |
| WORM storage | Compliance / accreditation |
| GPU orchestration | Heavy CV load |
| Advanced CV | After full stability |

---

## Artifact index

| Phase | Tool / doc |
|-------|------------|
| 1 | `tools/deploy_staging.py`, `tools/go_live_preflight.py` |
| 2 | `tools/verify_operational_signals.py`, Grafana/Loki/Tempo |
| 3 | `infra/pentest/` |
| 4 | `tests/test_pentest_hardening.py`, `tests/test_chaos_resilience.py` |
| 5 | `infra/runbooks/CANARY_ROLLOUT.md` |
| 6 | `infra/runbooks/DEPLOYMENT.md` |

**Discipline:** execute → validate → observe → harden
