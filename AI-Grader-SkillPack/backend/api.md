# Key API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/batch-grade/{assignment_id}` | Start batch grading |
| `GET /api/batch-grade-progress/{id}` | Poll progress |
| `GET /api/batch-grade-latest/{id}` | Latest batch meta |
| `GET /api/batch-meta/{batch_id}` | Verify batch exists |
| `GET /batch-results/{batch_id}` | Results HTML |
| `GET /api/download-report-word/{sub_id}` | Word export |
| `POST /api/preflight-evidence/{id}` | Preflight scan |

Rate-limit exempt: batch-results GET, batch-grade-progress GET
