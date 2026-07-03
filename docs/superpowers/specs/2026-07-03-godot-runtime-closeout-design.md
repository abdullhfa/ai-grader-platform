# Godot Runtime Closeout — Design Spec

**Date:** 2026-07-03  
**Status:** Approved — Ready for Implementation  
**Fixture strategy:** **C** — submission 50 + one student Godot + one corpus fixture (see §16)  
**Path:** `docs/superpowers/specs/2026-07-03-godot-runtime-closeout-design.md`  
**Checklist (short):** `docs/superpowers/specs/godot-closeout-checklist.md`  
**Depends on:**
- `2026-07-02-pro-gameplay-verification-design.md` (L4/Gate layer)
- `2026-07-03-deterministic-bp3-bp4-design.md` (B.P3/B.P4 — **closed for Ahmad case**)

---

## 1. Executive Decision

**Focus:** Godot hardening until deterministic production readiness.  
**Do not start** Unity, GameMaker, Python/HTML games, or Scratch until Godot meets Definition of Done (§8).

**Strategy:** Engine-by-engine, not feature-by-feature. One engine fully closed → next engine inherits the same contract pattern.

---

## 2. Current State (2026-07-03)

| Area | Status |
|------|--------|
| B.P3 / B.P4 deterministic (PRO) | ✅ Stable across regrades (`DESIGN_EVIDENCE_RULE_V1`, `VISUAL_DESIGN_RULE_V1`) |
| C.P5 / C.P6 Gate (when gameplay succeeds) | ✅ Opens at L4_partial + test doc (PRO ≥1 entry) |
| Grade **P** on submission 50 | ⚠️ Achieved when `gameplay_entered=true`; **U** when runtime flaky |
| MenuNavigator boot wait + single retry | ⚠️ Partial — not yet Godot-specific policy |
| Failure taxonomy | ❌ Not standardized — failures appear as vague U |
| Soak test matrix | ❌ Not automated |
| Word/UI failure reason | ❌ Incomplete — menu status string only, not institutional taxonomy |

**Remaining gap:** Godot runtime is **not production-closed** until launch → gameplay → Gate is reproducible or honestly classified.

---

## 3. Definition: “Godot 100% Complete”

Godot is complete when **all** rows in §8 (Definition of Done) pass. Partial success on B criteria alone is **insufficient**.

### 3.1 In-scope (Godot)

- Windows `.exe` export (legacy_exe path in sandbox)
- `MenuNavigator` boot / black screen / splash / delayed load
- `PlaytestOrchestrator` interaction after menu
- `assess_automated_l4_gate` → C.P5/C.P6 criterion_pass
- Failure classification + retry policy **Godot-only**
- Report/UI contract for runtime blockers

### 3.2 Out-of-scope (this closeout)

- Unity / GameMaker / HTML / Scratch engines
- Merit/Distinction gameplay depth (M3/D3 beyond honest L4)
- New AI grading models or rubric changes unrelated to runtime
- C.P6 “presentation quality” narrative (separate spec if needed)

---

## 4. Architecture

### 4.1 New module boundary (recommended)

```
app/godot_runtime/
  __init__.py
  failure_taxonomy.py    # classify_runtime_failure(), reason codes, AR labels
  retry_policy.py        # GodotRetryPolicy — boot/menu/interaction sequence
```

**Alternative (minimal):** Keep logic in `gameplay_verifier.py` + `runtime_observation_sandbox.py` with `engine_id == "godot"` guards.  
**Recommendation:** Small `godot_runtime/` package — keeps Unity/GM from inheriting Godot retries accidentally.

### 4.2 Data flow

```
runtime_observation_sandbox (Godot exe launch)
        ↓
GodotRetryPolicy.run()          # boot poll → nav pass #1 → playtest #1 → refocus → pass #2
        ↓
MenuNavigator + PlaytestOrchestrator (existing)
        ↓
classify_runtime_failure()      # single terminal reason if gameplay_entered=false
        ↓
gameplay_verification blob:
  - gameplay_entered
  - l4_level
  - failure_reason_code
  - failure_reason_ar
  - retry_attempts[]
        ↓
runtime_evidence_gate + finalizer (unchanged semantics — Gate only opens on honest L4)
        ↓
Word / UI / runtime.json (grading snapshot)
```

### 4.3 Invariants (no false positives)

1. `player_movement_verified` / `jump_detected` / `score_change_detected` **only** when `gameplay_entered=true`.
2. `l4_level` never `L4_partial` or `L4_full` without `gameplay_entered=true` and mechanics policy satisfied.
3. `criterion_pass.P5/P6` only when L4 gate rules pass — not smoke alone.
4. Retry does **not** promote achieved; it only improves detection or records classified failure.
5. B.P3/B.P4 deterministic seals remain untouched by runtime retry logic.

---

## 5. Task 1 — Failure Taxonomy

### 5.1 Terminal reason codes

Every Godot run that does not reach stable `gameplay_entered=true` (with honest mechanics) MUST end with **exactly one** primary code:

| Code | When |
|------|------|
| `BOOT_TIMEOUT` | Process started but boot polling exhausted (black screen / loading never cleared) |
| `BLACK_SCREEN_PERSISTENT` | Boot cleared partially but gameplay window remains black after full policy |
| `MENU_NOT_RESOLVED` | Menu detected but dismiss keys/clicks did not reach gameplay |
| `WINDOW_NOT_FOUND` | Game process exists but focus/capture could not target window |
| `NO_VISUAL_RESPONSE_TO_INPUT` | Gameplay or menu reached but no pixel/OCR change after interaction burst |
| `SERVER_DEPENDENCY_BLOCK` | OCR/dialog indicates network/server dependency (e.g. Connection Failed) |
| `PROCESS_CRASHED` | Child process exited unexpectedly during observation |
| `GAMEPLAY_ENTERED_BUT_NO_MECHANICS` | `gameplay_entered=true` but zero verified mechanics after playtest (L3 honesty — not a Pass path) |

Optional secondary tags (array): `slow_boot`, `ocr_low_confidence`, `retry_exhausted`.

### 5.2 API sketch

```python
@dataclass(frozen=True)
class GodotRuntimeFailure:
    code: str
    reason_ar: str
    reason_en: str
    evidence: dict  # boot_attempts, last_visual_state, ocr_snippet, process_exit_code

def classify_runtime_failure(
    *,
    window_detected: bool,
    black_screen_duration_s: float,
    gameplay_entered: bool,
    mechanics_verified_count: int,
    menu_status: str,
    visual_response: bool,
    server_dialog_detected: bool,
    process_crashed: bool,
    boot_timed_out: bool,
) -> Optional[GodotRuntimeFailure]:
    ...
```

### 5.3 Persistence surfaces

Must appear in **all** of:

| Surface | Field |
|---------|-------|
| `gameplay_verification` | `failure_reason_code`, `failure_reason_ar` |
| `artifact_inventory.runtime_observation_report` | same + `godot_runtime_closeout_v1` block |
| Grading snapshot / `runtime.json` export | same |
| UI `results.html` evidence table | Arabic institutional label |
| Word report (`report_feedback_formatter`) | Agent play summary + failure paragraph |

**Never:** raw JSON in Word; never “L4 جزئي” when `gameplay_entered=false`.

---

## 6. Task 2 — Godot Retry Policy

### 6.1 Policy scope

- Applies **only** when `engine_id in ("godot", "legacy_exe")` and platform Windows.
- Other engines use existing paths unchanged until their closeout.

### 6.2 Sequence (fixed order)

| Step | Action | Max duration / attempts |
|------|--------|-------------------------|
| 1 | Initial `GODOT_BOOT_WAIT` (6s) + boot poll (`BOOT_POLL_MAX`) | existing MenuNavigator constants |
| 2 | Menu navigation **pass #1** (`MAX_ATTEMPTS`) | 8 attempts |
| 3 | Playtest interaction burst **#1** (PlaytestOrchestrator) | plan default |
| 4 | If `gameplay_entered=false`: refocus window + recapture baseline | 1 cycle |
| 5 | Menu navigation **pass #2** | 8 attempts |
| 6 | Playtest interaction burst **#2** | plan default |
| 7 | Terminal `classify_runtime_failure()` | — |

Log each step in `retry_attempts[]` for soak analysis.

### 6.3 Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — Extend current single retry in `run_automated_gameplay_verification` | Tiny diff | Not Godot-scoped; no structured log |
| B — `GodotRetryPolicy` class (recommended) | Testable, engine-scoped, auditable | +1 module |
| C — Celery re-run entire grade on failure | Simple ops | Expensive, hides root cause |

**Recommendation:** **Option B.**

---

## 7. Task 3 — Soak Test Matrix

### 7.1 Script

New: `scripts/godot_soak_test.py`

- Runs N regrades per fixture (default N=3).
- Records: `gameplay_entered`, `l4_level`, `failure_reason_code`, grade, B.P3/B.P4, C.P5/C.P6.
- Exit code 0 iff success criteria met (§7.2).

### 7.2 Matrix (minimum)

| Fixture | Type | Runs | Source |
|---------|------|------|--------|
| Submission 50 (Ahmad Bakr) | menu + gameplay | 3 | DB + `uploads/students/bx72/...` |
| Godot simple direct | direct gameplay | 3 | TBD path or calibration corpus `l1_godot_export_00*` |
| Godot slow boot / menu | slow boot | 3 | TBD path or synthetic fixture |

**Success:** ≥ **8/9** runs produce **correct** outcome (Pass band when gameplay truly entered; classified failure otherwise).  
**Failure:** Any silent flip (same fixture: P then U with no reason code change) = soak fail.

### 7.3 Submission 50 close criterion

**3 consecutive** regrades where either:
- All three: `grade_level=P`, B.P3/B.P4/C.P5/C.P6 achieved, **or**
- All three: same `failure_reason_code` with honest U (no flip-flop).

---

## 8. Task 4 — Word / UI / Governance Contract (Freeze)

### 8.1 UI + Word must always show

1. **Agent play:** `L3` / `L4_partial` / `L4_full` — derived from `gameplay_verification`, not AI text.
2. **Failure reason** (Arabic) when runtime blocked — from taxonomy, not generic “لم يُثبت التشغيل”.
3. **Separation:** file evidence vs runtime evidence (existing badges — verify no regression).
4. **No raw JSON** in Word feedback.
5. **No AI praise** contradicting governance demotion (existing sanitizer — verify with soak failures).
6. **B.P3/B.P4 authority** visible when sealed (`DESIGN_EVIDENCE_RULE_V1`, `VISUAL_DESIGN_RULE_V1`).

### 8.2 Governance freeze rules

- Runtime retry/taxonomy changes **must not** demote sealed B.P3/B.P4.
- `HUMAN_REVIEW_REQUIRED` on C.P6 must not apply when `criterion_pass.P6=true` (already fixed — regression test required).
- `format_agent_play_summary_ar` must use `failure_reason_ar` when present.

---

## 9. Task 5 — Definition of Done (Godot Closed)

Godot may be declared **closed** only when **all** are true:

| ID | Criterion | Verification |
|----|-----------|--------------|
| A | Submission 50: 3 consecutive regrades stable (P or same classified U) | `scripts/regrade_submission_50_pro.py` ×3 or soak script |
| B | ≥2 additional Godot projects pass soak (§7.2) | `scripts/godot_soak_test.py` report |
| C | No false positives: no movement/jump verified without `gameplay_entered` | unit + soak assertions |
| D | Word/UI/Governance contract (§8) passes manual spot-check on pass + fail runs | checklist sign-off |
| E | Results reproducible: failure always has `failure_reason_code` | snapshot audit |

**After close:** Create git tag or checklist sign-off date in `godot-closeout-checklist.md` → then Unity closeout spec may begin.

---

## 10. Files to Touch (implementation)

| File | Change |
|------|--------|
| `app/godot_runtime/failure_taxonomy.py` | **New** — codes + classifier |
| `app/godot_runtime/retry_policy.py` | **New** — Godot retry orchestration |
| `app/gameplay_verifier.py` | Wire Godot policy; extend `MenuNavigationResult` with failure fields |
| `app/runtime_observation_sandbox.py` | Godot branch calls retry policy; attach taxonomy to report |
| `app/report_feedback_formatter.py` | Failure reason in Word |
| `app/templates/batch_results.html` | Failure code badge |
| `scripts/godot_soak_test.py` | **New** — matrix runner |
| `scripts/regrade_submission_50_pro.py` | Optional: `--runs 3` stability mode |
| `tests/test_godot_failure_taxonomy.py` | **New** — classifier unit tests |
| `tests/test_godot_retry_policy.py` | **New** — mocked sequence tests |
| `tests/test_pro_gameplay_verification.py` | Extend — no false L4 without gameplay |

---

## 11. Test Plan

### 11.1 Unit

- Each taxonomy code reachable from classifier inputs.
- Classifier returns exactly one primary code.
- Retry policy logs attempts; does not set `gameplay_entered=true` without visual evidence.
- `GAMEPLAY_ENTERED_BUT_NO_MECHANICS` forces L3, not L4_partial.

### 11.2 Integration

- Mock sandbox: SERVER_DEPENDENCY_BLOCK from Connection Failed OCR.
- Mock: BOOT_TIMEOUT after exhausted poll.
- Regression: B.P3/B.P4 stable when runtime fails.

### 11.3 Soak (manual/CI nightly)

- Full matrix §7.2 — artifact paths committed or documented in script README.

---

## 12. Rollout Order

1. Failure taxonomy + unit tests  
2. Godot retry policy wired in sandbox  
3. Word/UI surfaces for failure codes  
4. Soak script + run matrix  
5. Fix flakes until DoD §9 passes  
6. Sign off `godot-closeout-checklist.md` → **Godot closed**  
7. **Then** draft `2026-07-XX-unity-runtime-closeout-design.md`

---

## 13. Engine Roadmap (post-Godot)

1. Unity  
2. GameMaker  
3. Python games  
4. HTML games  
5. Scratch (if distinct runtime path)

Each engine gets its own closeout spec cloning §4–§9 structure; **no shared retry policy** until engine-specific behavior is validated.

---

## 14. Open Questions — Resolved

1. **Fixture paths (strategy C — approved):** See §16.
2. **CI:** Soak tests manual / pre-release gate (not every PR) — ~15–30 min wall time.
3. **SERVER_DEPENDENCY_BLOCK:** Always honest U with explicit reason — no silent Pass.

---

## 16. Soak Fixture Matrix (Strategy C)

| # | Fixture ID | Source | Path / ID | Profile |
|---|------------|--------|-----------|---------|
| 1 | `submission_50` | Student (baseline) | DB submission **50** → `uploads/students/bx72/.../P_03.exe` | menu + loading + real export |
| 2 | `student_godot_2` | Student (production) | **Discover at Task 0** via `scripts/godot_soak_fixtures.json` — scan `uploads/students/**/*.exe` + DB; skip network-dependent | direct gameplay OR simple menu OR cleaner export |
| 3 | `corpus_l1_godot_export_001` | Calibration corpus | `app/calibration/runtime_evidence_corpus/cases/l1_godot_export_001/game.exe` | stable regression fixture |

**Local workspace note (2026-07-03):** Only one student `.exe` exists (`bx72` / Ahmad). Task 0 must register a second student when uploaded, or document blocker in checklist until DoD **B** can pass.

### Per-run soak record (required fields)

Each run row in soak JSON/CSV:

```json
{
  "fixture_id": "submission_50",
  "run_index": 1,
  "gameplay_entered": true,
  "l4_level": "L4_partial",
  "failure_reason_code": null,
  "criterion_pass_p5": true,
  "criterion_pass_p6": true,
  "grade_level": "P",
  "timestamp": "ISO-8601"
}
```

---

## 17. Godot Touch Matrix (modification contract)

Graphify-validated boundary for Godot closeout. **Any Task 2+ change must respect this matrix.**

### 17.1 Zones

| Zone | Policy | Meaning |
|------|--------|---------|
| **GREEN** | Modify allowed | Godot runtime scope — implement taxonomy, retry, soak, Godot engine helpers |
| **YELLOW** | Wiring only | Read/write `failure_reason_*` or promote L4 — **no semantic change** to Gate/grade rules |
| **RED** | Do not touch | Frozen layers — no edits during Godot closeout unless explicit regression fix |

### 17.2 GREEN — allowed files

| Path | Role |
|------|------|
| `app/godot_runtime/**` | Taxonomy, retry policy, Godot-only helpers |
| `app/gameplay_verifier.py` | `MenuNavigator`, `run_automated_gameplay_verification`, `format_agent_play_summary_ar`, `calculate_l4_level` |
| `app/runtime_observation_sandbox.py` | Godot exe branch (~739–810), `capture_runtime_screenshot`, `analyze_godot_pck` |
| `app/runtime_engines/godot/**` | Export/smoke — Godot only |
| `app/window_focus_manager.py`, `app/runtime_interaction_trace.py` | Refocus / interaction burst |
| `scripts/godot_soak_*`, `scripts/discover_godot_soak_fixtures.py` | Soak matrix |
| `tests/test_godot_*`, `tests/test_menu_navigator.py`, `tests/test_pro_gameplay_verification.py` | Regression |

### 17.3 YELLOW — wiring only (no semantics change)

| Path | Allowed change |
|------|----------------|
| `app/runtime_criterion_mapping.py` | Pass-through of L4 gate certification (`l4_gate_certified`) |
| `app/runtime_evidence_gate.py` | `_promote_l4_gate_row` when `criterion_pass` honest |
| `app/report_feedback_formatter.py` | Display `failure_reason_ar` — no raw JSON |
| `app/templates/batch_results.html` | Failure code badge |
| `app/criteria_result_finalizer.py` | Reconcile after gate — no B-band rewrite |
| `app/batch_grader.py` | Pass full `artifact_inventory` / `engine_id` only |

### 17.4 RED — forbidden during Godot closeout

| Path | Reason |
|------|--------|
| `app/design_evidence_assessor.py` | B.P3/B.P4 deterministic — closed |
| `app/rubric/deterministic_engine.py` | B.P3/B.P4 seals |
| `app/btec_criteria_governance.py` | Sealed authority demotion rules |
| `app/btec_grade_resolution.py` | Institutional grade logic |
| `app/runtime_engines/unity/**`, `app/runtime_engines/gamemaker/**` | Other engines |
| `app/governance_failure_taxonomy.py` | Unrelated taxonomy |
| AI grading layers in `batch_grader.py` | No refactor |

### 17.5 Wiring points (Task 2)

Only **three** integration points may connect `app/godot_runtime/` to the pipeline:

1. `run_automated_gameplay_verification` → `GodotRetryPolicy`
2. `runtime_observation_sandbox` → pass `engine_id` + OCR/server flags to classifier inputs
3. `format_agent_play_summary_ar` + Word/UI → consume `failure_reason_code` / `failure_reason_ar`

Downstream (Gate, adjudication, grade) **reads** `gameplay_verification` — must not be redesigned.

---

## 15. Spec Self-Review (inline)

- [x] No TBD in DoD or taxonomy codes  
- [x] Consistent with engine-by-engine decision  
- [x] B.P3/B.P4 scope explicitly frozen  
- [x] Scope bounded to Godot — Unity deferred  
- [x] Open questions limited to fixtures/CI/policy edge case  
