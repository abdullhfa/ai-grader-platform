# Human cohort workshop log

Store manual pilot incidents and observations here.

## Files

| File | Content |
| ---- | ------- |
| `observations.jsonl` | Governance observation worksheets (B–D) |
| `incidents.jsonl` | Acute GFM incidents |
| `mitigations.jsonl` | Mitigation outcomes |

## API

| Endpoint | Use |
| -------- | --- |
| `GET /governance-pilot/batch/{batch_id}` | Observatory UI |
| `POST /api/governance-pilot/observation` | Save worksheet |
| `GET /api/governance-pilot/synthesis/batch/{batch_id}` | Batch synthesis |
| `POST /api/governance-workshop/incident` | Incident log |

See [`GOVERNANCE_PILOT_WORKSHEET_v1.md`](../GOVERNANCE_PILOT_WORKSHEET_v1.md) and [`COHORT_OBSERVATORY_WORKFLOW_v1.md`](../COHORT_OBSERVATORY_WORKFLOW_v1.md).
