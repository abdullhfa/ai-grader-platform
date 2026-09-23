# Godot Authoritative GV Production Wiring

**Date:** 2026-07-03  
**Status:** Approved for implementation  
**Goal:** Word/PDF production grading uses the same richest `gameplay_verification` as soak.

---

## Problem

Soak calls `resolve_authoritative_gameplay_verification` and writes GV back to `grading_result`. Production `attach_grading_mode_metadata` builds summaries via `_gameplay_verification_blob`, which previously preferred weak obs GV before synced result — causing L3 labels and blocked C.P5/C.P6 gates in Word while soak showed L4_partial.

---

## Solution

1. **`sync_authoritative_gv(inv, result) -> bool`** in `app/gameplay_verifier.py`
   - Calls `resolve_authoritative_gameplay_verification` (unchanged).
   - Writes GV to `grading_result`, `artifact_inventory`, and `runtime_observation_report`.
   - Returns False if no non-empty GV.

2. **Production wiring** — `attach_grading_mode_metadata` calls `sync_authoritative_gv` before `build_gameplay_verification_summary`.

3. **Soak** — `scripts/godot_soak_test.py` uses `sync_authoritative_gv`; snapshot richness fallback preserved.

4. **`_gameplay_verification_blob`** — prefer `grading_result["gameplay_verification"]` first, then inv, then obs, then nested fallbacks.

5. **`format_agent_play_summary_ar`** — L3 runtime-without-gameplay uses explicit Arabic guidance (not generic "Gate محجوب").

---

## Out of scope (unchanged)

- `resolve_authoritative_gameplay_verification` scoring/heuristics
- BTEC prerequisite logic and academic `achieved`
- Runtime/soak baseline fixtures and capture policy

---

## Definition of Done

- Unit tests: `test_gameplay_verifier_authoritative_wiring.py`
- `test_attach_grading_mode_metadata_uses_authoritative_gv` in grading profiles
- Regression: soak-related tests, capture stability, orchestrator wiring
- Regrade `submission_50` PRO: `gameplay_entered=true`, `L4_partial`, Word Godot section matches soak gates
- Checklist updated in `godot-closeout-checklist.md`

---

## Sign-off item

"Authoritative GV wired into production: full_grade Word/PDF matches soak for submission_50 (l4_level, gameplay_entered, criterion_pass_p5/p6)"
