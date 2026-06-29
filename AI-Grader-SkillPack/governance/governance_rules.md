# BTEC Governance Rules

Module: `app/btec_criteria_governance.py`

## Functions (order inside `apply_btec_criteria_governance`)

1. `enforce_feedback_achieved_consistency` — demote if feedback contradicts achieved=True
2. `enforce_execution_artifact_requirements` — P5/P6/P7/M3 need game artifacts (informative inventory only)
3. `apply_btec_awardability` — set `awardable` per cumulative BTEC rules
4. `enforce_not_achieved_feedback_consistency` — align feedback when achieved=False
5. `sanitize_all_criteria_feedback` — strip governance prefixes

## Cumulative awardability

- All Pass criteria `achieved` → eligible for P
- All Pass + all Merit `achieved` → eligible for M
- All Pass + Merit + Distinction `achieved` → eligible for D
- Any mandatory Pass missing → **U** (even if Merit achieved)

## Early vs full governance

Early stub (in `grade_student_submission`) runs **without** artifact inventory — must NOT demote on empty inventory (`_has_informative_artifact_signal` guard).
