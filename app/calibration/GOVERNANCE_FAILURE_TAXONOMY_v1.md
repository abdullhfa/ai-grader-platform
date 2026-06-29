# Governance Failure Taxonomy v1

**Not** a grading error taxonomy.  
Classifies **governance breakdown modes** — how institutional semantics fail.

Companion: [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md), [`HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md`](HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md)

Implementation: `app/governance_failure_taxonomy.py`

---

## Purpose

Transform the pilot from:

```text
system trial
```

into:

```text
institutional governance observatory
```

Every drift event, pilot incident, and reviewer confusion maps to a **failure mode**.

---

## Failure modes (frozen)

| ID | Mode | Example |
| --- | ---- | ------- |
| `GFM_AUTHORITY_INFLATION` | authority inflation | L3 treated as verification |
| `GFM_CONTRADICTION_INVISIBILITY` | contradiction invisibility | replay omits downgrade |
| `GFM_SEMANTIC_ESCALATION` | semantic escalation | «confirmed» / «verified» wording |
| `GFM_REPLAY_INCOMPLETENESS` | replay incompleteness | missing provenance step |
| `GFM_FALSE_CORROBORATION` | false corroboration | weak hints treated strongly |
| `GFM_MODALITY_DOMINANCE` | modality dominance | video overrides code contradiction |
| `GFM_DRIFT_SILENCE` | drift silence | freeze violation undetected |
| `GFM_BOUNDARY_OMISSION` | boundary omission | exe present, no coverage notice |
| `GFM_REVIEWER_AUTHORITY_CONFUSION` | reviewer confusion | manual — L2 called verified |
| `GFM_TRUST_EROSION` | trust erosion | manual — post-disagreement trust loss |

---

## Automatic classification

Drift monitor signals → taxonomy via `classify_drift_signal()`.

Temporal / cross-artifact signals → `classify_consistency_signal()`.

Cohort reports include `failure_taxonomy.mode_counts`.

---

## Manual workshop incidents

Log schema:

```json
{
  "submission_id": 9,
  "incident_type": "reviewer_l3_confusion",
  "reviewer_confused_l3": true,
  "trust_eroded": false,
  "notes_ar": "..."
}
```

Classify with `classify_workshop_incident()` → store under `app/calibration/human_cohort_workshop/`.

---

## Non-goals

- Using taxonomy to auto-change grades
- Treating failure mode as «student cheating»
- Expanding taxonomy mid-pilot without v2 RFC

---

## Pre-sandbox gate

Pilot observatory complete when:

- Top 3 failure modes documented with mitigations
- `GFM_AUTHORITY_INFLATION` rate stable or declining
- Manual `GFM_TRUST_EROSION` incidents reviewed in workshop
