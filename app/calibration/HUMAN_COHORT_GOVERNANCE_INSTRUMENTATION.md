# Human Cohort Governance Instrumentation

Companion to [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md).

---

## Purpose

The next pilot is **not**:

```text
testing the AI
```

It is:

```text
testing the governance freeze under real human disagreement
```

First real **governance validation** — not capability validation.

---

## Cohort size

**20–30 submissions** with at least one human verifier / assessor per disputed or borderline case.

---

## Metrics (frozen for pilot_v1)

| Metric | Definition | Target signal |
| ------ | ---------- | ------------- |
| `replay_presence_rate` | Submissions with `authority_replay` or `evidence_trace_graph` | > 0.95 after re-grade |
| `replay_consultation_rate` | **Manual** — verifier opened `/authority-replay/{id}` | Track in workshop log |
| `drift_detection_rate` | Submissions flagged by `governance_drift_monitor` | Monitor — should not rise silently |
| `claim_flag_surface_rate` | Submissions with `claim_authority_flags` | Transparency baseline |
| `contradiction_visibility_rate` | Inventory shows temporal/cross-artifact signals | Must stay visible |
| `downgrade_acceptance` | **Manual** — reviewers accept downgrade semantics | Workshop rubric |
| `HOLD_utilization` | **Manual** — human HOLD when ambiguity unresolved | Workshop log |
| `l3_verification_confusion_rate` | Text/reviewer treats L3 as verification | **Should → 0** |
| `authority_confusion_incidents` | **Manual** — reviewer said «verified» for L1–L3 only | Qualitative log |
| `trust_retention` | **Manual** — trust after disagreement session | Survey / workshop |

Implementation: `app/governance_drift_monitor.py` → `analyze_cohort_governance_metrics()`.

Failure mode taxonomy: [`GOVERNANCE_FAILURE_TAXONOMY_v1.md`](GOVERNANCE_FAILURE_TAXONOMY_v1.md)

Response protocols: [`GOVERNANCE_RESPONSE_PROTOCOLS_v1.md`](GOVERNANCE_RESPONSE_PROTOCOLS_v1.md) — severity S1–S5 + export gates.

Mitigation memory: [`GOVERNANCE_MITIGATION_MEMORY_v1.md`](GOVERNANCE_MITIGATION_MEMORY_v1.md) — outcome tracking + effectiveness rates.

---

## API

| Endpoint | Use |
| -------- | --- |
| `GET /api/governance-drift/{submission_id}` | Per-submission drift vs freeze |
| `GET /api/governance-drift/batch/{batch_id}` | Cohort aggregate metrics |
| `GET /governance-pilot/batch/{batch_id}` | Observatory UI — governance worksheet |
| `GET /api/governance-pilot/worksheet/{submission_id}` | Worksheet prefill (Section A) |
| `POST /api/governance-pilot/observation` | Save Sections B–D |
| `GET /api/governance-pilot/synthesis/batch/{batch_id}` | Institutional stability report |
| `POST /api/governance-workshop/incident` | Acute GFM incident log |

Worksheet spec: [`GOVERNANCE_PILOT_WORKSHEET_v1.md`](GOVERNANCE_PILOT_WORKSHEET_v1.md)  
Workflow: [`COHORT_OBSERVATORY_WORKFLOW_v1.md`](COHORT_OBSERVATORY_WORKFLOW_v1.md)

---

## Workshop log fields (manual)

Record per review session:

```json
{
  "submission_id": 9,
  "reviewer_id": "...",
  "opened_authority_replay": true,
  "hold_applied": false,
  "downgrade_understood": true,
  "authority_confusion": false,
  "notes_ar": "..."
}
```

Store in `app/calibration/human_cohort_workshop/` (create at pilot start).

---

## Success criteria (governance — not accuracy)

1. No silent `L4`/`L5` auto-assignment
2. `contradiction → downgrade` visible in replay for all flagged cases
3. Zero increase in forbidden claim language week-over-week
4. Reviewers can reconstruct claim provenance without reading raw AI prompt
5. Disagreement sessions do not collapse to «AI said so»

---

## Explicit non-goals for pilot

- Benchmarking model accuracy vs teachers
- Expanding to sandbox mid-pilot
- Changing GOVERNANCE_FREEZE_v1 semantics without RFC

---

## Pre-sandbox gate

Sandbox (L4) requires:

- [ ] Cohort workshop complete
- [ ] `drift_detection_rate` stable or explained
- [ ] `l3_verification_confusion_rate` = 0 in workshop sample
- [ ] GOVERNANCE_FREEZE_v2 RFC if any semantic change needed
