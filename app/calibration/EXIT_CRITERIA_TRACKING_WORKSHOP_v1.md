# EXIT CRITERIA TRACKING WORKSHOP v1

**Workshop ID:** `EXIT_CRITERIA_TRACKING_WORKSHOP_v1`  
**Status:** ACTIVE — evidence accumulation layer (not system development · not activation)  
**Prerequisite:** [`PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.md`](PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.md) exit criteria  
**Parallel track:** [`TRUSTED_REPLAY_DISCIPLINE_PILOT_v1.md`](TRUSTED_REPLAY_DISCIPLINE_PILOT_v1.md)

Machine-readable: [`EXIT_CRITERIA_TRACKING_WORKSHOP_v1.json`](EXIT_CRITERIA_TRACKING_WORKSHOP_v1.json)  
Metrics ledger: `human_cohort_workshop/exit_criteria_metrics.jsonl`  
UI hook (Section F): [`EPISTEMIC_TRACE_CAPTURE_SCHEMA_v1.json`](EPISTEMIC_TRACE_CAPTURE_SCHEMA_v1.json) · `governance_pilot_observatory` — observational only

---

## Institutional invariant

```text
Containment evidence is not activation evidence.
```

Arabic:

```text
دليل الاحتواء ليس دليل تفعيل.
```

This workshop **measures** whether mitigation changes behaviour over time — it does **not** authorize L4 · freeze v2 · or grading wire.

---

## Purpose

**Evidence accumulation layer** — not feature development.

Question:

```text
Does mitigation actually change epistemic behaviour across cohorts?
```

If metrics do not improve → architecture is **elegant but non-effective**.

---

## Relationship to Phase 4 RFC exit criteria

| RFC exit requirement | Tracking metric |
| -------------------- | --------------- |
| trusted replay discipline | `replay_before_judgment_rate` |
| breach recurrence reduction | `qb_recurrence` |
| (implicit) language containment | `vocabulary_drift_frequency` |
| automated quarantine enforcement | `quarantine_persistence` (proxy until wired) |
| no unresolved QB3/QB4 | `qb_recurrence` QB3/QB4 counts |
| provenance continuity | `provenance_continuity_success` |

**All RFC exit criteria remain unmet until this workshop demonstrates improvement across new cohorts.**

---

## Five fixed metrics (every future cohort)

| Metric ID | Question (AR) | What it measures |
| --------- | --------------- | ---------------- |
| `M1_replay_before_judgment_rate` | هل replay يسبق authority فعلاً؟ | `yes` / (`yes`+`partial`+`no`) from Section E |
| `M2_qb_recurrence` | هل QB2/QB3 تنخفض؟ | QB taxonomy counts per cohort (advisory eval) |
| `M3_vocabulary_drift_frequency` | هل لغة verified/achieved انخفضت؟ | `verification_language_used=yes` rate + forbidden shortcut samples |
| `M4_quarantine_persistence` | هل يبقى الحجر ثابتًا تحت temptation؟ | stable/maintained vs breach under pressure cases |
| `M5_provenance_continuity_success` | هل exe ↔ gameplay ↔ identity أصبحت مرتبطة؟ | identity match · replay consult · gameplay verified proxy |

### Recording format (per cohort)

```json
{
  "cohort_id": "batch_N",
  "recorded_at": "ISO-8601",
  "observation_count": 21,
  "metrics": {
    "M1_replay_before_judgment_rate": {"yes": 1, "partial": 16, "denominator": 21, "rate_yes": 0.048},
    "M2_qb_recurrence": {"QB2": 3, "QB3": 9, "QB4": 0, "none": 9},
    "M3_vocabulary_drift_frequency": {"verification_yes_rate": 0.524},
    "M4_quarantine_persistence": {"stable_or_maintained": 12, "breach": 9},
    "M5_provenance_continuity_success": {"replay_consulted_rate": 0.048, "identity_linked_proxy": "manual"}
  },
  "baseline_comparison": "REFERENCE_GOVERNANCE_COHORT_BATCH4",
  "improvement_demonstrated": false
}
```

---

## Baseline cohort — Batch 4 (reference)

**Cohort:** `REFERENCE_GOVERNANCE_COHORT_BATCH4` · **n=21**

| Metric | Baseline value | Interpretation |
| ------ | -------------- | -------------- |
| **M1** replay-before-judgment `yes` | **1/21 (4.8%)** | replay rarely precedes authority |
| **M1** `partial` | **16/21** | procedural replay — not trusted |
| **M1** `replay_consulted_at` set | **1/21** | provenance consult almost absent |
| **M2** QB2 | **3** | verification before replay |
| **M2** QB3 | **9** | runtime→achieved without provenance |
| **M2** QB4 | **0** | (none classified at advisory threshold) |
| **M3** verification_language `yes` | **11/21 (52%)** | high vocabulary drift |
| **M4** breach (QB2+) | **12/21** | quarantine not stable under temptation |
| **M5** provenance continuity | **weak** | #13 identity gap · 1/21 replay consult |

**Baseline verdict:** mitigation architecture documented — **behaviour change not yet demonstrated**.

---

## Workshop protocol

| Step | Action |
| ---- | ------ |
| 1 | Select cohort (new observations — not re-scoring Batch 4) |
| 2 | Compute five metrics from Phase 2 worksheets + advisory stubs |
| 3 | Append row to `exit_criteria_metrics.jsonl` |
| 4 | Compare to Batch 4 baseline — document delta |
| 5 | **Do not** interpret improvement as activation license |
| 6 | Report to epoch mitigation ledger |

### Success test (workshop — not activation)

```text
Across ≥2 new cohorts: statistically visible reduction in M2 QB2/QB3
AND M1 yes-rate increase AND M3 verification_yes decrease
→ recurrence reduction evidence (still not activation alone)
```

---

## Explicit non-goals

- Grading retune
- L4 sandbox activation
- GOVERNANCE_FREEZE_v2
- «Metrics green → deploy authority»
- Replacing human audit requirement

---

## Lineage

| Ref | Role |
| --- | ---- |
| `PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1` | exit criteria source |
| `EPOCH_REREVIEW_PACKET_PATH_A_v1` | containment progress verdict |
| `EPISTEMIC_QUARANTINE_CONTRACT_v1` | QB taxonomy |
| `REFERENCE_GOVERNANCE_COHORT_BATCH4` | baseline cohort |

**Facilitator:** Eng.Abdulah · **Activated:** 2026-05-25
