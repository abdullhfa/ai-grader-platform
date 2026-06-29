# Structured Reliability Review Workshop

**Source:** `app/calibration/reports/cal_reliability_stress_v2.json`  
**Run:** `cal_reliability_stress_v2`  
**Rows:** 14 diverse FP cases  
**Archetypes:** achievement_inflation_weak_code, borderline_sufficiency_near_pass, borderline_video_only_code, cross_modal_conflict, cross_modal_false_overlap, fake_runtime_fp_system, logs_without_systems, ocr_misleading_score100, ocr_video_without_corroboration, pattern_hints_only, runtime_fake_log_only, runtime_stale_no_temporal, screenshots_only, systems_without_runtime

## Purpose

Evaluate **human-operational interpretability** — not grading accuracy.

- Do **not** ask: «هل النظام صح؟»
- **Do** ask: «هل behavior مفهوم وقابل للتدقيق؟»

## Per row (fill `reliability_review_workshop_v1.json`)

| Question ID | Goal | Scale / notes |
| ----------- | ---- | ------------- |
| `review_escalation_logical` | gate usefulness | yes / partial / no / unclear |
| `reasoning_understandable` | interpretability | yes / partial / no / unclear |
| `insufficiency_clear` | academic explainability | yes / partial / no / unclear |
| `conflict_flags_useful` | operational clarity | yes / partial / no / unclear |
| `severity_appropriate` | escalation calibration | yes / partial / no / unclear |
| `noisy_triggers` | gate tuning later | free text in `notes` |
| `behavior_auditable` | institutional trust | yes / partial / no / unclear |

Also record: `friction_notes`, `operational_friction_tags` (e.g. `redundant_reason`, `severity_high_for_borderline`).

## After workshop

1. Summarize top **1–2** friction themes only → see `POST_WORKSHOP_SYNTHESIS.md`.
2. Aggregate tags: `python -m app.calibration.aggregate_workshop_friction --workshop app/calibration/workshop/reliability_review_workshop_v1.json --out app/calibration/workshop/workshop_synthesis_v1.json`
3. One scoped change per freeze window.
4. `run_reliability_stress_cycle` → `calibration_diff` → observe.

## Do not

- Wire shadow → achieved.
- Tune 5+ triggers at once.
- Treat stress FP rate as production KPI.
