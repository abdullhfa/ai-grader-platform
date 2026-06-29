# Governance Mitigation Memory v1

Companion: [`GOVERNANCE_RESPONSE_PROTOCOLS_v1.md`](GOVERNANCE_RESPONSE_PROTOCOLS_v1.md), [`GOVERNANCE_FAILURE_TAXONOMY_v1.md`](GOVERNANCE_FAILURE_TAXONOMY_v1.md)

Implementation: `app/governance_mitigation_memory.py`

---

## Purpose

Close the governance loop:

```text
failure → response → outcome → institutional learning
```

Not only incident handling — **did the mitigation work over time?**

---

## Record lifecycle

1. **Trigger** — grading produces `governance_responses` → `record_mitigation_from_drift()`
2. **Outcome** — workshop or auto recurrence → `record_mitigation_outcome()`
3. **Synthesis** — cohort API → `analyze_mitigation_effectiveness()`

Storage: `app/calibration/human_cohort_workshop/mitigations.jsonl`

---

## Outcomes (frozen)

| Outcome | Meaning |
| ------- | ------- |
| `pending` | mitigation applied, awaiting evaluation |
| `effective` | failure did not recur |
| `partial` | improved but ambiguity remains |
| `recurred` | same GFM appeared again |
| `ineffective` | no improvement |
| `unknown` | insufficient data |

---

## API

| Endpoint | Role |
| -------- | ---- |
| `POST /api/governance-mitigation/outcome` | Record workshop outcome |
| `GET /api/governance-mitigation/summary` | Effectiveness by GFM |
| `GET /api/governance-drift/batch/{id}` | Includes `mitigation_memory` |

---

## Example learning row

| Failure | Mitigation | Outcome |
| ------- | ---------- | ------- |
| GFM_MODALITY_DOMINANCE | downgrade visual hints | confusion decreased → effective |
| GFM_SEMANTIC_ESCALATION | wording review | no recurrence → effective |
| GFM_REPLAY_INCOMPLETENESS | replay rebuild | resolved → effective |

---

## Non-goals

- Using outcome to auto-change grades
- AI judging trust without human/workshop input for GFM_TRUST_*

---

## Pilot synthesis

Workshop reviews `by_failure_mode` effectiveness rates before sandbox gate.
