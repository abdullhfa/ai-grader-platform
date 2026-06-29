# Post-workshop synthesis (1 page)

Fill after completing `reliability_review_workshop_v1.json`.

## After workshop — two paths only

Read `workshop_synthesis_v1.json` → answer: **Is change operationally justified?**

### Path 1 — No actionable clusters → HOLD

```text
freeze current baseline
  → no Run3
  → no threshold changes
  → no feature work
  → continue observation quietly
```

This is **governance restraint success**, not “no work”. Later, wait for: new operational evidence, real cohort growth, repeated workshop signals, drift over time — not “find something to change”.

### Path 2 — Single actionable cluster → smallest justified Run3

```text
one friction only
one scoped change only
freeze window
run calibration / stress cycle
calibration_diff
observe drift
stop again
```

Not: multiple improvements, redesign, optimization wave, feature expansion. After Run3: **observe stability again** — not “start Run4”.

## Aggregate friction

```powershell
python -m app.calibration.aggregate_workshop_friction `
  --workshop app/calibration/workshop/reliability_review_workshop_v1.json `
  --out app/calibration/workshop/workshop_synthesis_v1.json
```

## Questions (answer in prose — max 1 page)

1. **Top friction theme (one)** — must appear in `actionable_friction_clusters` from synthesis JSON (≥4 rows or ≥35% share on 14-row workshop):  
   e.g. `redundant_rubric_shadow_reason`, `severity_too_high`, `unclear_cross_modal`.  
   Ignore tags that appear only 1–2 times (anecdote).

2. **Second theme (optional, only if strong):**

3. **Rows least auditable** (workshop_row + archetype):

4. **Proposed Run3 change (one sentence):**  
   Interpretability refinement only — merge flags, simplify reasoning, calm severity. No new modalities.

5. **What we will NOT change this window:**

## Run3 discipline

- Freeze window: `freeze_reliability_stress_v3`
- One scoped change
- `run_reliability_stress_cycle` → `calibration_diff` (v2 baseline)
- Success = clearer behavior + `drift_severity` low + FP/FN stable — not lower FP rate on stress cohort
