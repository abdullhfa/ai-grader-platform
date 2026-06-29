# Gold dataset (teacher labels)

One row per **(submission_id × criterion)**.

## Required fields

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `submission_id` | string | Must match `system_snapshots.json` key |
| `criterion` | string | e.g. `P3`, `A.P3` |
| `teacher_result.achieved` | bool | Teacher ground truth |
| `teacher_result.confidence` | float | Optional 0–1 |

## Strongly recommended (large-scale calibration)

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `teacher_notes` | string[] | Free-text reviewer notes |
| `accepted_evidence` | string[] | What teacher accepted |
| `rejected_evidence` | string[] | What teacher rejected |
| `teacher_evidence_strength` | weak \| moderate \| strong | Evidence quality band |
| `review_complexity` | easy \| moderate \| ambiguous | Human effort / ambiguity |
| `reviewer_taxonomy` | string[] | Confirmed error tags (overrides heuristics) |

## Schema versions

- `unity_calibration_gold_v1` — `unity_gold_submission_v1.json` (exemplar rows)
- `unity_calibration_gold_v2` — same fields + `cohort_tags`, `submission_archetype` (optional stratification)

## Synthetic cohort

`unity_gold_synthetic_cohort_v1.json` is generated for **pipeline testing only** (`synthetic: true`). Do not treat as teacher ground truth.

## Reliability stress cohort

`unity_gold_reliability_stress_v1.json` — **failure-oriented operational simulation** (~50 designed archetypes: fake runtime, OCR misleading, noisy upload, borderline sufficiency, etc.). `stress_cohort: true`. Not production validation.

```powershell
python -m app.calibration.run_reliability_stress_cycle
```

## Alignment

Export system output with:

```powershell
python -m app.calibration.export_system_snapshots --input-dir <grading_exports> --out app/calibration/gold_dataset/system_snapshots.json
```

Each snapshot should include `criteria_results`, `evidence_layer`, `rubric_sufficiency_shadow`, `human_review_gates` when produced by current batch grader.

## Real cohort pilot (first 20–30) — not engineering

**Prerequisite:** workshop complete → valid `workshop_synthesis_v1.json` → HOLD or single scoped Run3 only.

Goal: test whether behavior stays **calm / interpretable / governable** with real teachers — not production-ready claim.

| Step | Action |
| ---- | ------ |
| 1 | Collect 20–30 real submissions (diverse: strong, weak, borderline, noisy, partial) |
| 2 | Teachers label `unity_gold_real_pilot_v1.json` (one row per submission × criterion) |
| 3 | Run batch grader **without threshold changes**; export `system_snapshots_real_pilot_v1.json` |
| 4 | `run_large_scale_calibration` under new freeze window (e.g. `freeze_real_pilot_v1`) |
| 5 | Observe only: FP rate, `fp_empty_evidence_layer`, review inflation, pattern_hint dependence — **do not fix quickly** |
| 6 | Optional: `export_human_review_workshop` on real pilot report |
| 7 | `calibration_diff` only after a deliberate single change in a **new** freeze window |
| 8 | Move rarely — trust erosion is slower and more dangerous than technical bugs |

Do not: shadow → achieved, daily threshold tweaks, production claim from stress/synthetic cohorts.
