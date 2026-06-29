# Deployment Runbook

## Prerequisites

- PostgreSQL 16+ (production)
- Redis 7+
- MinIO or S3-compatible object store
- Optional: RabbitMQ, Vault, ClamAV

## Stack (Docker Compose)

**Production base:**

```bash
cd infra/docker
docker compose -f docker-compose.yml -f docker-compose.ops.yml up --build -d
```

**Staging (recommended before go-live):**

```bash
cd infra/docker
docker compose \
  -f docker-compose.yml \
  -f docker-compose.ops.yml \
  -f docker-compose.staging.yml \
  up --build -d

python ../../tools/staging_smoke.py --base-url http://localhost:8000
```

See `STAGING_VALIDATION.md` for the full validation matrix.

## Required environment

```env
DATABASE_URL=postgresql+psycopg2://aigrader:aigrader@postgres:5432/aigrader
AI_GRADER_REDIS_URL=redis://redis:6379/0
AI_GRADER_OBJECT_STORE=s3
AI_GRADER_S3_ENDPOINT=http://minio:9000
AI_GRADER_CELERY_ENABLED=1
AI_GRADER_ASYNC_MALWARE_SCAN=1
AI_GRADER_MALWARE_SCAN=1
```

## Health checks

| Endpoint | Expected |
|----------|----------|
| `GET /api/health` | 200 |
| `GET /api/ready` | 200 |
| `GET /api/contracts/validate` | `ok: true` |
| `GET /api/ops/dashboard` | metrics payload |

## Worker pools

| Queue | Worker image |
|-------|--------------|
| `runtime_jobs` | worker-runtime |
| `gameplay_jobs` / `cv_jobs` | worker-cv |
| `reasoning_jobs` | worker-reasoning |
| `malware_jobs` | worker-runtime (add `-Q malware_jobs`) |

## Post-deploy verification

1. Submit test grading → confirm replay snapshot created
2. Open `/governance/examiner` → replay investigation loads
3. `GET /api/security/tamper/replay/{key}/{session}` → `integrity: verified`
4. Run DR drills: `pytest tests/test_dr_drills.py`
