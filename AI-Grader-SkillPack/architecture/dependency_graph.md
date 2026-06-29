# Dependency Graph (grading path)

```
grade_batch_async
  └─ grade_single_student
       ├─ grade_student_submission (AI)
       │    └─ apply_btec_criteria_governance [EARLY STUB - no inventory]
       └─ _finalize_grading_result_after_ai
            ├─ run_deterministic_rubric
            ├─ apply_runtime_criterion_adjudication
            ├─ apply_criterion_authority_guardrails
            ├─ apply_btec_criteria_governance [FULL]
            ├─ apply_pro_pearson_btec_package
            └─ finalize_grading_criteria_results
                 ├─ reconcile_authoritative_achieved
                 ├─ apply_deliverable_game_criteria_pass
                 └─ apply_runtime_evidence_gate  ← TERMINAL
batch_grade_worker
  └─ finalize_grading_criteria_results (again)
  └─ DB commit + PDF
```

## Bypass risks (fixed)

- Early governance without inventory → false "no project files" demotion
- Finalizer promoting P5/P6 after governance → blocked by `runtime_gate_block`
- UI reading stale `institutional_resolution` → cache invalidated on gate demotion
