# Governance Pilot Worksheet v1

**Not a grading sheet.**  
**Yes:** `governance observation worksheet`

Companion: [`COHORT_OBSERVATORY_WORKFLOW_v1.md`](COHORT_OBSERVATORY_WORKFLOW_v1.md)

UI: `/governance-pilot/batch/{batch_id}`  
API: `GET /api/governance-pilot/worksheet/{submission_id}` · `POST /api/governance-pilot/observation`

---

## Per submission

### Section A — Runtime Evidence State (auto-prefill)

| Field | Example | Source |
| ----- | ------- | ------ |
| runtime level | L2 | `artifact_inventory.runtime_evidence_level` |
| executable detected | yes | inventory |
| gameplay video | yes | inventory |
| runtime verified | no | L5 only — human |
| contradiction flags | modality divergence | cross/temporal consistency |
| replay available | yes/no | `authority_replay` in snapshot |

**Note:** Section A describes **system state** — not reviewer judgment.

---

### Section B — Reviewer Behaviour (manual)

| Question | Answer |
| -------- | ------ |
| Did reviewer interpret L3 as verification? | yes / no |
| Was replay opened? | yes / no |
| Was downgrade accepted? | yes / no |
| Did reviewer override authority boundary? | yes / no |
| Was HOLD considered? | yes / no |
| Was HOLD applied? | yes / no |
| Notes (AR) | free text |

---

### Section C — Governance Events (manual + suggested from drift)

| Event | Typical severity |
| ----- | ---------------- |
| GFM_MODALITY_DOMINANCE | S3 |
| GFM_AUTHORITY_INFLATION | S4 |
| GFM_REPLAY_INCOMPLETENESS / replay omission | S2 |
| GFM_REVIEWER_AUTHORITY_CONFUSION | S4 |
| GFM_TRUST_EROSION | S4 |
| GFM_DRIFT_SILENCE | S5 |

Add/remove events per workshop discussion.

---

### Section D — Trust Signals (manual, 1–5)

| Metric | Scale |
| ------ | ----- |
| reviewer confidence | 1–5 |
| trust retained after disagreement | 1–5 |
| ambiguity understandable | 1–5 |

---

## JSON payload (API)

```json
{
  "submission_id": 12,
  "batch_id": 16,
  "reviewer_id": "verifier_1",
  "section_b_reviewer_behaviour": {
    "l3_interpreted_as_verification": false,
    "replay_opened": true,
    "downgrade_accepted": true,
    "authority_boundary_overridden": false,
    "hold_considered": true,
    "hold_applied": false,
    "notes_ar": "..."
  },
  "section_c_governance_events": [
    {"event": "GFM_MODALITY_DOMINANCE", "severity": "S3"}
  ],
  "section_d_trust_signals": {
    "reviewer_confidence": 4,
    "trust_retained_after_disagreement": 4,
    "ambiguity_understandable": 3
  }
}
```

Stored in: `app/calibration/human_cohort_workshop/observations.jsonl`

---

## After workshop — batch synthesis

`GET /api/governance-pilot/synthesis/batch/{batch_id}`

Output type: **`institutional_governance_stability_report`** — not AI accuracy report.

Key outputs:

| Output | Why |
| ------ | --- |
| Top GFMs | Where semantics collapse |
| Replay usage patterns | Is provenance useful? |
| L3 confusion map | Do humans understand authority? |
| Trust retention | Does disagreement destroy trust? |
| Mitigation effectiveness | Do loops work? |
| Export gate interventions | Is governance enforced? |
| `ready_for_l4_rfc` | Pilot gate boolean |

---

## Pilot gate (L4 RFC)

Proceed to L4 sandbox RFC only if:

- [ ] L3 confusion rate manual = **0** in workshop sample
- [ ] Replay consultation rate ≥ **50%** (or explained)
- [ ] Downgrade understood in workshop
- [ ] Trust retained avg ≥ **3/5**
- [ ] No silent S5 drift
- [ ] Top GFMs documented + mitigations recorded

**Forbidden after workshop:** prompt tuning, model swaps, L4 sandbox — until synthesis reviewed.
