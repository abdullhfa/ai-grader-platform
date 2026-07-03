# Godot Closeout Checklist

**Reference:** `2026-07-03-godot-runtime-closeout-design.md`  
**Rule:** Do **not** start Unity / GameMaker / other engines until every box below is checked.

---

## Implementation order

- [x] **1. Failure taxonomy** — 8 codes in `app/godot_runtime/failure_taxonomy.py`
- [x] **2. Godot retry policy** — boot → nav#1 → play#1 → refocus → nav#2 → play#2 → classify
- [x] **3. Surfaces** — `failure_reason_code` + `failure_reason_ar` in snapshot, UI, Word (baseline `9fbf57e`)
- [x] **4. Soak test** — `scripts/godot_soak_test.py` matrix (3 fixtures × 3 runs = 9 active)
- [x] **5. Fix until stable** — 9/9 correct; submission_50 ×3 P; student_godot_2 ×3 `GAME_WINDOW_CAPTURE_FAILED`
- [ ] **6. Sign off** — date + commit hash below (pending human sign-off)

---

## Touch matrix (§17 contract)

| Zone | Rule |
|------|------|
| **GREEN** | `godot_runtime/`, `gameplay_verifier` (nav/play), `runtime_observation_sandbox` (Godot exe), `runtime_engines/godot/`, soak scripts/tests |
| **YELLOW** | Gate/adjudication/finalizer/Word/UI — wiring `failure_reason_*` only |
| **RED** | `design_evidence_assessor`, `deterministic_engine`, `btec_*` governance/grade, Unity/GM engines |

**Task 2 wiring only:** (1) `run_automated_gameplay_verification` → `GodotRetryPolicy` (2) sandbox → classifier flags (3) Word/UI → `failure_reason_code`

---

## Failure codes (must all be classifiable)

- [ ] `BOOT_TIMEOUT`
- [ ] `BLACK_SCREEN_PERSISTENT`
- [ ] `MENU_NOT_RESOLVED`
- [ ] `WINDOW_NOT_FOUND`
- [x] `GAME_WINDOW_CAPTURE_FAILED`
- [ ] `NO_VISUAL_RESPONSE_TO_INPUT`
- [ ] `SERVER_DEPENDENCY_BLOCK`
- [ ] `PROCESS_CRASHED`
- [ ] `GAMEPLAY_ENTERED_BUT_NO_MECHANICS`

---

## Invariants (no false positives)

- [ ] No `player_movement_verified` unless `gameplay_entered=true`
- [ ] No `L4_partial` / `L4_full` unless `gameplay_entered=true`
- [ ] Gate C.P5/C.P6 only when L4 `criterion_pass` honest
- [ ] B.P3/B.P4 deterministic seals not demoted by runtime layer
- [ ] Word: no raw JSON; Agent play label matches verification blob

---

## Soak matrix

| Fixture | Runs | Pass/Fail stable | Notes |
|---------|------|------------------|-------|
| Submission 50 | 3/3 | ☑ | 3× P, `gameplay_entered=true` — `godot_soak_20260703_170017.json` |
| Student Godot #2 | 3/3 | ☑ | ahmad hamtini `final.exe` — 3× `GAME_WINDOW_CAPTURE_FAILED` (stable_failure) |
| Corpus `l1_godot_export_001` | 3/3 | ☑ | 3× `PROCESS_CRASHED` |

**Target:** ≥8/9 correct outcomes; every failure has a reason code.

---

## Definition of Done

- [x] **A** — Submission 50: 3 consecutive regrades P (`submission_50_stable=true`)
- [x] **B** — student_godot_2 + corpus in soak matrix (stable outcomes)
- [ ] **C** — No movement/jump false positives (not re-verified this soak)
- [ ] **D** — Word/UI/Governance contract verified
- [x] **E** — Failures reproducible with `failure_reason_code`

---

## Sign-off

| Field | Value |
|-------|-------|
| Godot closed date | pending sign-off |
| Commit hash | (after implementation commit) |
| Soak report path | `reports/godot_soak_20260703_170017.json` |
| Trial reports | `reports/godot_trial_farst.json`, `reports/godot_trial_final.json` |
| Signed by | |

**Next engine after sign-off:** Unity (`unity-runtime-closeout-design.md` — not started)
