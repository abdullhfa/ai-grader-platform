# Calibration freeze windows

Large-scale calibration must use **frozen** configuration between runs. Do not tune thresholds daily inside a freeze window.

## What is frozen

| Artifact | Env / field | Notes |
| -------- | ----------- | ----- |
| Rubric sufficiency contracts | `RUBRIC_VERSION` | Declarative contracts in `rubric_sufficiency_contracts.py` |
| Human review gates | `HUMAN_REVIEW_GATES_VERSION` | Trigger registry in `human_review_gates.py` (v1.1: sparse+corrupt intake → medium packaging, not critical) |
| Evidence schema | `evidence_layer.schema_version` | Normalized evidence items |
| Corroboration engine | `runtime_corroboration.engine_version` | Modality weights |
| Cross-modal | `cross_modal_corroboration.version` | Window / diversity rules |
| Extractor versions | `EXTRACTOR_VERSION`, per-modality versions | Unity / PT / Excel extractors |
| Achieved grading (LLM) | **Out of scope for shadow tuning** | Shadow layers must not drive `achieved` |

Record every run in report `reliability_run`:

- `run_id` — `CALIBRATION_RUN_ID` (e.g. `cal_2026_05_20_w01`)
- `freeze_window_id` — logical label (e.g. `freeze_2026_q2_w1`)
- `generated_at_utc`
- Input paths: gold + system snapshots

## Discipline

1. **One change per window** — After a freeze window ends, change at most one subsystem (e.g. only review gates OR only sufficiency thresholds).
2. **No shadow → achieved** — Do not wire `sufficiency_result.sufficient` or `human_review_required` into achieved until calibration sign-off.
3. **Store JSON per run** — `app/calibration/reports/<run_id>_calibration_report.json`
4. **Diff runs** — Compare `metrics`, `false_positive_density_report`, `shadow_dashboard`, `review_gate_dashboard` across `reliability_run.run_id`.

```powershell
python -m app.calibration.calibration_diff `
  --baseline app/calibration/reports/freeze_q2_w1.json `
  --candidate app/calibration/reports/freeze_q2_w2.json `
  --out app/calibration/reports/diff_q2_w1_vs_w2.json
```

## Commands

```powershell
# Export snapshots from saved batch/grading JSON (see export_system_snapshots.py)
python -m app.calibration.export_system_snapshots --input-dir path/to/exports --out app/calibration/gold_dataset/system_snapshots.json

# Full calibration report (teacher achieved vs system + shadow dashboards)
$env:CALIBRATION_RUN_ID = "cal_2026_05_20_w01"
$env:RUBRIC_VERSION = "1.0"
python -m app.calibration.run_large_scale_calibration `
  --gold app/calibration/gold_dataset/unity_gold_submission_v1.json `
  --systems app/calibration/gold_dataset/system_snapshots.json `
  --out app/calibration/reports/cal_2026_05_20_w01.json `
  --freeze-window freeze_2026_q2_w1
```

## Target cohort size

| Phase | Submissions | Notes |
| ----- | ----------- | ----- |
| Pilot | 30–50 | Real teacher labels, diverse quality |
| Large-scale | 100–300 | Required before production-ready claim |
| Synthetic pipeline test | 100 | `generate_synthetic_gold_cohort.py` — not teacher ground truth |
| Reliability stress simulation | 50 | `generate_reliability_stress_cohort.py` — failure-oriented; not production validation |

### Reliability stress cycle (freeze discipline still applies)

```powershell
python -m app.calibration.run_reliability_stress_cycle --count 50 --freeze-window freeze_reliability_stress_v1
```

Outputs: `gold_dataset/unity_gold_reliability_stress_v1.json`, `system_snapshots_reliability_stress_v1.json`, `reports/cal_reliability_stress_v1.json`.

### Human Review Workshop (structured interpretability)

```powershell
python -m app.calibration.export_human_review_workshop `
  --report app/calibration/reports/cal_reliability_stress_v2.json `
  --out-dir app/calibration/workshop
```

Fill `workshop/reliability_review_workshop_v1.json` — assess auditable behavior, not «هل النظام صح؟».

## Institutional cadence (operational rhythm)

Long-term survivability depends on **predictable tempo**, not constant intervention.

| Activity | Suggested cadence |
| -------- | ----------------- |
| Workshop review | Each freeze cycle (or after meaningful cohort) |
| Calibration run | Only when cohort has enough real teacher labels |
| Threshold / gate changes | Rare; one subsystem per freeze window |
| Run3-type changes | Scoped + justified only; then stop |
| Governance review | Slower than engineering review |

Record in reports and synthesis: **why we changed**, **why we held**, **why anecdote ≠ cluster** — institutional decision memory, not only metrics.

Slow drift to watch: escalation fatigue, ignored medium severity, reasoning duplication, flag dependence, normalization of noise. Prefer **calm observation** over rapid optimization.

**Prerequisite now:** complete workshop → aggregate → `governance_signal_valid: true` → HOLD or smallest Run3 → then first real pilot (20–30).

Populate `gold_dataset/unity_gold_submission_v1.json` (or v2) with real `submission_id` values aligned to exported snapshots.
