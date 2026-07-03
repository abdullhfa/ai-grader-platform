# Submission 50 Capture Stability — PRO Game Window Readiness

**Date:** 2026-07-03  
**Status:** Approved  
**Parent:** `2026-07-03-godot-runtime-closeout-design.md`  
**Depends on:** `2026-07-03-godot-orchestrator-wiring-design.md` (Option C — implemented)  
**Blocks:** Godot Closeout `submission_50_stable` until soak `--runs 3` passes

---

## 1. Problem

Soak matrix `godot_soak_20260703_040253.json` shows **zero blocking bugs** (wiring/consumer defense works) but **`submission_50_stable=false`**:

| Run | `gameplay_entered` | `failure_reason_code` | Grade |
|-----|-------------------|----------------------|-------|
| 1 | `true` | — | P |
| 2 | `true` | — | P |
| 3 | `false` | `NO_VISUAL_RESPONSE_TO_INPUT` | U |

Forensic comparison of `runtime/runtime.json` for the three runs reveals Run 3 is **not** a GodotRetryPolicy gameplay-classification flake:

| Signal | Run 1–2 (pass) | Run 3 (fail) |
|--------|----------------|--------------|
| `godot_retry_attempts` | `nav_pass_1` → `play_pass_1` | **None** |
| P_03.exe screenshots | 16 (menu_nav, req_*) | **4** (launch, post_interaction, mid_runtime, pre_exit) |
| `terminal_classify` | — | `smoke_post_loop` |
| `interaction_trace.errors` | `[]` | `game_window capture failed for player_movement/before — desktop_fallback not permitted in PRO mode` |

**Root cause:** `PlaytestOrchestrator._capture_tagged` raises `EvidenceQualityError` when `capture_scope != "game_window"` in PRO mode. The exception aborts `run_automated_gameplay_verification` before `GodotRetryPolicy` completes. The smoke loop `except` path falls back to `run_interaction_burst()` and `_attach_terminal_godot_classify_if_missing`, which mislabels the outcome as `NO_VISUAL_RESPONSE_TO_INPUT`.

Historical sessions for submission 50 show the same capture error intermittently — instability is **window focus / game_window capture timing**, not menu navigation or visual-delta thresholds.

---

## 2. Goal

Make PRO Godot observation **deterministic enough** for closeout:

1. **Retry capture** before failing — refocus + probe before nav/play and inside `_capture_tagged`.
2. **Honest taxonomy** — distinguish capture pipeline failure from window absence and from zero visual delta after successful captures.
3. **Stable soak** — submission 50 ×3 either all pass (`gameplay_entered=true`, grade P) or all fail with the **same documented code** (not a mix of P and misclassified U).

---

## 3. Failure code semantics (approved)

Add **9th terminal code** `GAME_WINDOW_CAPTURE_FAILED`. Keep existing codes unchanged.

| Code | When to use | When **not** to use |
|------|-------------|---------------------|
| `WINDOW_NOT_FOUND` | No game window handle / process window not detected at all | Process running but capture pipeline rejects scope |
| `GAME_WINDOW_CAPTURE_FAILED` | Godot process alive; PRO capture probe or tagged capture failed after retries (`capture_scope` still `desktop_fallback` or capture error) | Window never launched |
| `NO_VISUAL_RESPONSE_TO_INPUT` | `gameplay_entered=true` or nav reached gameplay; **successful** `game_window` captures; inputs sent; visual delta / mechanics verification shows no response | Capture never succeeded; policy aborted early |

**Arabic label (approved intent):**  
`تعذّر التقاط نافذة اللعبة للتحقق — اللعبة تعمل لكن Agent لم يحصل على لقطة gameplay صالحة.`

**Evidence fields** (minimum on `failure_evidence`):

```json
{
  "window_detected": true,
  "process_alive": true,
  "capture_scope_last": "desktop_fallback",
  "capture_retries_exhausted": true,
  "probe_phase": "pre_flight | tagged_capture",
  "requirement_id": "player_movement",
  "phase": "before"
}
```

---

## 4. Approach (Option A + taxonomy fix — approved)

Three coordinated changes:

1. **Pre-flight gate** in `GodotRetryPolicy.run` — focus + capture probe before `nav_pass_1`.
2. **Capture retry** in `PlaytestOrchestrator._capture_tagged` — up to 3 attempts with refocus.
3. **Exception path correction** in `runtime_observation_sandbox.smoke_test_windows_exe` — map capture failures to `GAME_WINDOW_CAPTURE_FAILED`, not terminal `NO_VISUAL_RESPONSE_TO_INPUT`.

---

## 5. Task A — Pre-flight gate (GodotRetryPolicy)

**File:** `app/godot_runtime/retry_policy.py` (GREEN)

### 5.1 Behavior

Before `_nav_pass("nav_pass_1", ...)`:

1. Call `focus_game_window(process_pid=process_pid)`.
2. Run a lightweight **capture probe** via the same `capture_screenshot` closure passed to policy (label e.g. `capture_probe_0`).
3. Accept probe when `shot.get("capture_scope") == "game_window"` and `shot.get("status") == "captured"`.
4. On failure: sleep `CAPTURE_RETRY_INTERVAL_S` (default **0.5**), refocus, retry up to **`CAPTURE_PROBE_MAX_ATTEMPTS`** (default **5**).

### 5.2 Early exit

If all probe attempts fail:

- Return `GodotRetryOutcome` with:
  - `gameplay_entered=false`
  - `failure=GodotRuntimeFailure(code="GAME_WINDOW_CAPTURE_FAILED", ...)`
  - `retry_attempts=[{"step": "capture_preflight", "passed": false, "attempts": 3}]`
- **Do not** enter `MenuNavigator` or `PlaytestOrchestrator`.

### 5.3 Non-goals

- Do not relax PRO rule forbidding `desktop_fallback` captures in evidence package
- Do not change nav/play sequence (still nav#1 → play#1 → refocus → nav#2 → play#2)

---

## 6. Task B — Capture retry in PlaytestOrchestrator

**File:** `app/gameplay_verifier.py` (GREEN)

### 6.1 `_capture_tagged` retry loop

When `pro_mode=True` and first capture returns `capture_scope != "game_window"`:

1. Refocus game window (`focus_game_window(process_pid=...)`).
2. Sleep `CAPTURE_RETRY_INTERVAL_S` (0.5s).
3. Retry capture (same label/req_id/phase).
4. Repeat up to **`CAPTURE_TAGGED_MAX_ATTEMPTS`** (default **3** total attempts).

Only after exhausting retries: raise `EvidenceQualityError` with message unchanged for log compatibility, but attach structured hint:

```python
exc.capture_failure = True  # or dedicated CaptureFailureError subclass
```

Prefer **subclass** `CaptureFailureError(EvidenceQualityError)` so sandbox can catch narrowly without treating all evidence errors alike.

### 6.2 Shared constants

Define in `app/godot_runtime/retry_policy.py` or `app/gameplay_verifier.py` (single source):

```python
CAPTURE_PROBE_MAX_ATTEMPTS = 5
CAPTURE_TAGGED_MAX_ATTEMPTS = 3
CAPTURE_RETRY_INTERVAL_S = 0.5
```

### 6.3 MenuNavigator

Optional: reuse same retry helper for menu navigation screenshots if they hit the same PRO scope check. **Minimum scope:** `_capture_tagged` only (where Run 3 failed). Menu nav screenshots may follow in same PR if trivial.

---

## 7. Task C — Exception path (runtime_observation_sandbox)

**File:** `app/runtime_observation_sandbox.py` (GREEN)

### 7.1 Catch capture failures explicitly

In the `run_automated_gameplay_verification` try/except block (~L885):

```python
except CaptureFailureError as exc:
    out["gameplay_verification"] = build_capture_failure_gv(exc, process_pid=proc.pid)
    # minimal interaction_trace noting capture_failure — no run_interaction_burst as primary outcome
except Exception as exc:
    # existing burst fallback for unexpected errors only
```

`build_capture_failure_gv` sets:

- `failure_reason_code`: `GAME_WINDOW_CAPTURE_FAILED`
- `gameplay_entered`: `false`
- `terminal_classify`: `capture_pipeline` (not `smoke_post_loop`)
- `failure_evidence`: probe/tag context from exception

### 7.2 Terminal classify guard

Update `_attach_terminal_godot_classify_if_missing`:

- **Skip** when `interaction_trace.errors` contains capture-failure marker **or** when `gameplay_verification` already has `GAME_WINDOW_CAPTURE_FAILED`.
- **Never** emit `NO_VISUAL_RESPONSE_TO_INPUT` when `godot_retry_attempts` is absent **and** capture errors present in trace.

### 7.3 Consumer ensure alignment

Update `_ensure_failure_reason_code_on_negative_gameplay` in `gameplay_verifier.py`:

- If `interaction_trace.errors` mention `desktop_fallback not permitted` → prefer `GAME_WINDOW_CAPTURE_FAILED` over generic terminal classify.

---

## 8. Task D — Failure taxonomy

**File:** `app/godot_runtime/failure_taxonomy.py` (GREEN)

- Add `GAME_WINDOW_CAPTURE_FAILED` to `FAILURE_CODES` tuple.
- Add Arabic label to `_LABELS_AR`.
- Add helper `classify_capture_failure(**evidence) -> GodotRuntimeFailure` — explicit factory; **do not** overload `classify_runtime_failure` boolean flags (capture failure is orthogonal to `visual_response`).

**Do not** change ordering/logic of existing 8 codes in `classify_runtime_failure`.

---

## 9. Touch matrix

| Zone | Files | Rule |
|------|-------|------|
| **GREEN** | `godot_runtime/retry_policy.py`, `godot_runtime/failure_taxonomy.py`, `gameplay_verifier.py` (capture + ensure), `runtime_observation_sandbox.py` (Godot exe smoke path), tests | Allowed |
| **YELLOW** | `report_feedback_formatter.py`, Word/UI | Wire new code label only if formatter maps codes by name (likely automatic via existing gv fields) |
| **RED** | `deterministic_engine`, `btec_*`, Unity/GM engines, B.P3/B.P4 | Forbidden |

---

## 10. Testing

### 10.1 Unit tests

| Test | Assert |
|------|--------|
| `test_capture_preflight_fails_with_game_window_capture_failed` | Policy returns failure without nav steps |
| `test_capture_tagged_retries_before_evidence_error` | Mock capture: fail×2, succeed×3 → no exception |
| `test_capture_tagged_exhausted_raises_capture_failure_error` | 3× desktop_fallback → `CaptureFailureError` |
| `test_sandbox_maps_capture_failure_not_no_visual` | Exception path gv code == `GAME_WINDOW_CAPTURE_FAILED` |
| `test_failure_taxonomy_includes_game_window_capture_failed` | Code in `FAILURE_CODES` + Arabic label |

### 10.2 Integration / soak

```powershell
python scripts/godot_soak_test.py --runs 3
```

**Pass criteria (submission 50):**

- `blocking_bug_count == 0` (preserved from Option C)
- `submission_50_stable == true`:
  - **Either** 3× `gameplay_entered=true`, grade P
  - **Or** 3× same `failure_reason_code` (acceptable if capture remains environment-blocked)
- Run 3 must **not** show `NO_VISUAL_RESPONSE_TO_INPUT` with only 4 screenshots and empty `godot_retry_attempts`

---

## 11. Documentation updates

| File | Change |
|------|--------|
| `docs/superpowers/specs/godot-closeout-checklist.md` | Add `GAME_WINDOW_CAPTURE_FAILED` to failure codes list |
| `docs/superpowers/specs/2026-07-03-godot-runtime-closeout-design.md` | Cross-reference this spec in § failure taxonomy (optional footnote) |

---

## 12. Out of scope

- Lowering PRO capture quality bar (allowing `desktop_fallback` in evidence package)
- Changing visual-delta thresholds for `NO_VISUAL_RESPONSE_TO_INPUT`
- `student_godot_2` fixture upload (parallel track — DoD B; not blocked by this spec)
- Unity / GameMaker capture paths

---

## 13. Success definition

Godot closeout **capture-stability slice** is done when:

1. New code deployed and tests green (§10.1).
2. Soak `--runs 3` meets §10.2 pass criteria.
3. If still unstable with **consistent** `GAME_WINDOW_CAPTURE_FAILED`, document as environment/permissions follow-up — not a wiring blocking bug.

Full Godot Closeout still requires DoD B (`student_godot_2` ×3) per parent spec.

---

## 14. Decision log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Failure code for capture pipeline | **`GAME_WINDOW_CAPTURE_FAILED`** (new) | Distinguishes running exe + failed PRO capture from `WINDOW_NOT_FOUND` and from `NO_VISUAL_RESPONSE_TO_INPUT` |
| Primary fix | Pre-flight + tagged retry | Addresses root cause (timing/focus), not mislabeling alone |
| Retry counts | 3 × 0.5s | Bounded latency (~1.5s extra worst case); matches existing boot poll granularity |
| Probe attempts (v2) | **5** × 0.5s | Raised after soak evidence showed 2/3 preflight fails with 3 attempts |
