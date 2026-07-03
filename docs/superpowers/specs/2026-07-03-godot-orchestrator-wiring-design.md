# Godot Orchestrator Wiring + Consumer Defense + Soak Harness

**Date:** 2026-07-03  
**Status:** Approved (option C)  
**Parent:** `2026-07-03-godot-runtime-closeout-design.md`  
**Blocks:** Godot Closeout sign-off until soak matrix passes with populated fields

---

## 1. Problem

Batch PRO grading uses `app/runtime/orchestrator.py`, which merges nested `legacy_observation` / `godot_observation` into `runtime_observation_report`. The merge whitelist **omits** `gameplay_verification` and `interaction_trace`.

`GodotRetryPolicy` runs inside `smoke_test_windows_exe` and writes `gameplay_verification` (including `failure_reason_code`, `failure_reason_ar`, `gameplay_entered`) onto the nested observation. Orchestrator completes with `engine=legacy_exe`, `status=completed`, but top-level `runtime_observation_report.gameplay_verification` stays empty.

**Symptoms observed:**

- Soak report: `gameplay_entered=null`, `failure_reason_code=null` despite runtime completing
- Unit/integration tests pass (direct sandbox path promotes fields correctly)
- Background soak `--runs 3` aborted by harness (~300ms); foreground `--runs 1` completed but with empty Godot fields

---

## 2. Goal

Ensure every PRO Godot batch grade and soak run produces **honest, classifiable** runtime evidence at the surfaces that consume `gameplay_verification`:

| Surface | Required |
|---------|----------|
| `runtime_observation_report.gameplay_verification` | dict (may indicate failure; never silently absent after exe smoke) |
| `failure_reason_code` | non-null when `gameplay_entered=false` |
| `gameplay_entered` | explicit `true` or `false` (not `null`) after Godot exe PRO observation |
| Soak JSON | every run documented; exceptions never silent |

---

## 3. Approach (Option C — approved)

Three layers:

1. **A — Orchestrator wiring (source fix)**
2. **B — Consumer defense (fallback + warning)**
3. **Soak harness hardening (operational guard)**

---

## 4. Task A — Orchestrator wiring

**File:** `app/runtime/orchestrator.py` (YELLOW — field promotion only)

### 4.1 Promote fields from nested observations

When merging `legacy_observation` or `godot_observation`, also promote when present:

| Field | Priority |
|-------|----------|
| `gameplay_verification` | Required promotion |
| `interaction_trace` | Required promotion |
| `runtime_interaction_trace` | Alias — promote if `interaction_trace` absent |

**Precedence:** if both `legacy_observation` and `godot_observation` provide `gameplay_verification`, prefer the one with richer payload (non-empty `failure_reason_code` or `gameplay_entered is not None`; else last-wins godot over legacy).

### 4.2 Propagation to inventory

No change to `batch_grader` semantics — orchestrator output becomes `artifact_inventory.runtime_observation_report`. Once promoted, existing downstream paths (`attach_grading_mode_metadata`, soak extractor, Word/UI) receive fields without further wiring.

### 4.3 Non-goals

- Do not change Gate rules, grade resolution, or B.P3/B.P4
- Do not alter Unity/GameMaker orchestrator branches

---

## 5. Task B — Consumer defense

**File:** `app/gameplay_verifier.py` — `_gameplay_verification_blob()` and `_interaction_trace()` (GREEN)

### 5.1 Fallback search order

When top-level blob is empty, search in order:

1. `observation.gameplay_verification`
2. `inventory.gameplay_verification`
3. `observation.signals.legacy_observation.gameplay_verification`
4. `observation.signals.godot_observation.gameplay_verification`
5. `observation.legacy_observation.gameplay_verification` (flattened alias if present)
6. First `artifact_analyses[].gameplay_verification` with non-empty dict

Same pattern for `interaction_trace` / `runtime_interaction_trace`.

### 5.2 Warning contract

When fallback path (3–6) is used:

- Log once per resolution: `logger.warning("gameplay_verification_fallback", extra={source, submission_id})`
- Set `gv["_resolution_source"] = "<path>"` on returned dict (internal; not shown in Word/UI)

**Purpose:** fallback is safety net, not the happy path. Warnings surface orchestrator regressions in logs.

### 5.3 Non-goals

- `report_feedback_formatter.py` does not implement its own search — it consumes `build_gameplay_verification_summary()` only
- `runtime_criterion_mapping.py` unchanged (semantics frozen)

---

## 6. Task C — Soak harness hardening

**File:** `scripts/godot_soak_test.py` (GREEN)

### 6.1 Per-run exception handling

Wrap each fixture run in `try/except`:

```json
{
  "fixture_id": "submission_50",
  "run_index": 2,
  "status": "error",
  "error": "RuntimeError: ...",
  "traceback": "...",
  "gameplay_entered": null,
  "failure_reason_code": null,
  "correct": false
}
```

### 6.2 Always write report

- `main()` writes JSON even when matrix aborts mid-run
- `atexit` or `finally` ensures partial report on unhandled exit
- Exit code 1 when evaluation fails; **never** exit 0 with empty/missing report file

### 6.3 Logging

- `print(..., flush=True)` on every run start/end
- Optional `--log-file reports/godot_soak_latest.log`
- Report includes `harness_version`, `duration_ms` per run

### 6.4 Foreground requirement

Document in script docstring: full matrix must run in **foreground** (~15–20 min per submission_50 run). Background harness may abort long processes.

---

## 7. Blocking bug — Godot Closeout gate

**Explicit rule (approved):**

> For any PRO Godot exe observation where `runtime_observed=true` or smoke completed with process launch attempted:  
> **`gameplay_verification` empty OR `gameplay_entered=null` OR failure without `failure_reason_code`**  
> = **blocking bug — Godot Closeout cannot proceed.**

This applies to:

- `runtime_observation_report` in grading snapshot
- `runtime.json` export / manifest under `uploads/runtime_sessions/`
- Every row in `reports/godot_soak_*.json` (except `skipped` fixtures)

Soak success criteria (unchanged from parent spec):

- ≥ 8/9 runs **correct** (pass band when gameplay entered; classified failure otherwise)
- submission_50: 3 consecutive stable outcomes
- Zero runs with `status=completed` observation and empty `gameplay_verification`

---

## 8. Touch matrix (this spec)

| Zone | Path | Change |
|------|------|--------|
| YELLOW | `app/runtime/orchestrator.py` | Promote `gameplay_verification`, `interaction_trace` |
| GREEN | `app/gameplay_verifier.py` | Fallback blob resolution + warning |
| GREEN | `scripts/godot_soak_test.py` | Exception capture, partial report, flush logging |
| GREEN | `tests/test_godot_orchestrator_wiring.py` | New — orchestrator promotion + fallback unit tests |

**RED:** unchanged from parent spec §17.4

---

## 9. Testing

| Test | Asserts |
|------|---------|
| `test_orchestrator_promotes_gameplay_verification` | Nested `legacy_observation.gameplay_verification` → top-level observation |
| `test_gameplay_verification_blob_fallback` | Top-level empty; nested populated → blob returned + `_resolution_source` |
| `test_soak_writes_partial_report_on_error` | Mock failing grade → JSON file exists with `status=error` |
| Regression | `test_godot_retry_policy`, `test_pro_gameplay_verification`, `test_report_feedback_formatter` |

**Manual verification:**

```powershell
python scripts/godot_soak_test.py --runs 3
```

Inspect latest `reports/godot_soak_*.json` — no null `gameplay_entered` on completed Godot exe runs.

---

## 10. Success criteria

- [ ] Orchestrator promotes `gameplay_verification` + `interaction_trace`
- [ ] Consumer fallback with warning when orchestrator regresses
- [ ] Soak never silent-exits; partial JSON on failure
- [ ] Foreground soak `--runs 3`: submission_50 ×3 + corpus ×3 documented
- [ ] Blocking bug rule enforced in soak evaluation (`empty_gv_on_completed_smoke` counter → fail)
- [ ] Parent closeout checklist §4 soak row can be signed

---

## 11. Out of scope

- Unity / GameMaker orchestrator changes
- New failure taxonomy codes
- B.P3 / B.P4 / Gate semantic changes
- `student_godot_2` fixture (remains pending until upload)
