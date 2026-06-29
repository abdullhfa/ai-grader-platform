# Governance Response Protocols v1

Companion: [`GOVERNANCE_FAILURE_TAXONOMY_v1.md`](GOVERNANCE_FAILURE_TAXONOMY_v1.md), [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md)

Implementation: `app/governance_response_protocols.py`

Transforms:

```text
observing governance failures
```

into:

```text
governance self-correction
```

---

## Severity levels (S1–S5)

| Level | Label | Risk | Human required |
| ----- | ----- | ---- | -------------- |
| S1 | wording drift | low | no |
| S2 | replay omission | low–medium | no |
| S3 | hidden contradiction | medium | yes |
| S4 | authority escalation | high | yes |
| S5 | silent false verification | critical | yes |

Used uniformly by: drift monitor, replay viewer, cohort API, export gates.

---

## Response matrix (frozen)

| Failure Mode | Severity (default) | Response |
| ------------ | ------------------ | -------- |
| GFM_SEMANTIC_ESCALATION | S1 | sanitize language + log overclaim |
| GFM_REPLAY_INCOMPLETENESS | S2 | flag export + rebuild replay |
| GFM_BOUNDARY_OMISSION | S2 | inject coverage notice |
| GFM_FALSE_CORROBORATION | S3 | mark weak hint authority |
| GFM_CONTRADICTION_INVISIBILITY | S3 | surface in replay + downgrade |
| GFM_MODALITY_DOMINANCE | S3 | downgrade visual hints |
| GFM_AUTHORITY_INFLATION | S4 | freeze escalation + wording review |
| GFM_DRIFT_SILENCE | S5 | governance alert + halt expansion |
| GFM_REVIEWER_* (manual) | S4–S5 | mandatory human moderation |

---

## Export gates

| Gate | Meaning |
| ---- | ------- |
| `none` | export allowed |
| `advisory_warning` | export with governance warning |
| `conditional_block` | export requires review (provenance gap) |
| `block_until_review` | export blocked until human moderation |

**Does not mutate grades** — institutional export / review policy only.

---

## Integration

- `governance_drift` on grading snapshot includes `governance_responses`
- Authority Replay viewer shows severity + recommended actions
- Word/PDF export may consult `export_policy.allow_export` (future wire)

---

## Non-goals

- Auto Not Achieved from GFM
- Auto grade adjustment from severity
- AI simulating trust erosion responses without manual GFM
