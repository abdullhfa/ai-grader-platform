# Debugging Prompt

When debugging a false U grade:

1. Read `grading_snapshot_json` for submission
2. Check `runtime_evidence_gate` block in snapshot
3. Check `btec_criteria_governance.changes`
4. Verify `artifact_inventory.runtime_artifacts.scratch_detected`
5. Check if `finalize_grading_criteria_results` ran after governance
6. Compare `achieved` vs `awardable` per criterion
