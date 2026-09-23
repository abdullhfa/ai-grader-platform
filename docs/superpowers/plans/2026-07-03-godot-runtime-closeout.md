# Godot Runtime Closeout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Godot runtime for production — deterministic failure taxonomy, Godot-only retry policy, soak matrix (strategy C), Word/UI contract, sign-off before any other engine.

**Architecture:** New `app/godot_runtime/` package (`failure_taxonomy.py`, `retry_policy.py`) wired from `run_automated_gameplay_verification` / `runtime_observation_sandbox` when `engine_id` is Godot/legacy_exe. Soak runner writes structured JSON per run. B.P3/B.P4 deterministic seals untouched.

**Tech Stack:** Python 3.11+, pytest, existing `MenuNavigator` / `PlaytestOrchestrator`, SQLite submissions DB, calibration corpus fixtures.

**Spec:** `docs/superpowers/specs/2026-07-03-godot-runtime-closeout-design.md`  
**Checklist:** `docs/superpowers/specs/godot-closeout-checklist.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `app/godot_runtime/__init__.py` | Package exports |
| `app/godot_runtime/failure_taxonomy.py` | 8 terminal codes + `classify_runtime_failure()` |
| `app/godot_runtime/retry_policy.py` | `GodotRetryPolicy.run()` — boot/nav/play ×2 |
| `app/gameplay_verifier.py` | Delegate Godot path; extend result blobs |
| `app/runtime_observation_sandbox.py` | Godot branch → retry policy |
| `app/report_feedback_formatter.py` | Failure reason in Word |
| `app/templates/batch_results.html` | Failure badge in UI |
| `scripts/godot_soak_fixtures.json` | Fixture registry (strategy C) |
| `scripts/godot_soak_test.py` | Matrix runner + JSON report |
| `tests/test_godot_failure_taxonomy.py` | Classifier unit tests |
| `tests/test_godot_retry_policy.py` | Mocked retry sequence tests |

---

### Task 0: Fixture registry (strategy C)

**Files:**
- Create: `scripts/godot_soak_fixtures.json`
- Create: `scripts/discover_godot_soak_fixtures.py`

- [ ] **Step 1: Create fixture JSON**

```json
{
  "version": 1,
  "fixtures": [
    {
      "id": "submission_50",
      "kind": "db_submission",
      "submission_id": 50,
      "profile": "menu_loading_real"
    },
    {
      "id": "corpus_l1_godot_export_001",
      "kind": "corpus_exe",
      "path": "app/calibration/runtime_evidence_corpus/cases/l1_godot_export_001/game.exe",
      "profile": "regression_stable"
    },
    {
      "id": "student_godot_2",
      "kind": "student_folder",
      "path": null,
      "profile": "direct_or_simple_menu",
      "pending": true,
      "notes": "Filled by discover_godot_soak_fixtures.py — must not be network-dependent"
    }
  ],
  "runs_per_fixture": 3,
  "required_run_fields": [
    "gameplay_entered",
    "l4_level",
    "failure_reason_code",
    "criterion_pass_p5",
    "criterion_pass_p6",
    "grade_level"
  ]
}
```

- [ ] **Step 2: Discovery script** — scan `uploads/students/**/*.exe`, prefer folder with `.gd` and no `Connection Failed` in prior runs; update `student_godot_2.path` and set `pending: false`.

Run: `python scripts/discover_godot_soak_fixtures.py`  
Expected: prints fixture list; if only Ahmad exe, `student_godot_2` stays `pending: true` (DoD B blocked until second upload).

- [ ] **Step 3: Commit**

```bash
git add scripts/godot_soak_fixtures.json scripts/discover_godot_soak_fixtures.py
git commit -m "chore: add Godot soak fixture registry (strategy C)"
```

---

### Task 1: Failure taxonomy

**Files:**
- Create: `app/godot_runtime/__init__.py`
- Create: `app/godot_runtime/failure_taxonomy.py`
- Create: `tests/test_godot_failure_taxonomy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_godot_failure_taxonomy.py
import pytest
from app.godot_runtime.failure_taxonomy import (
    FAILURE_CODES,
    classify_runtime_failure,
)


def test_process_crashed_takes_priority():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="unknown",
        visual_response=False,
        server_dialog_detected=False,
        process_crashed=True,
        boot_timed_out=False,
    )
    assert r is not None
    assert r.code == "PROCESS_CRASHED"


def test_server_dependency_block():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=2,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="menu",
        visual_response=False,
        server_dialog_detected=True,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r.code == "SERVER_DEPENDENCY_BLOCK"


def test_gameplay_entered_but_no_mechanics():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=True,
        mechanics_verified_count=0,
        menu_status="gameplay_entered",
        visual_response=True,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r.code == "GAMEPLAY_ENTERED_BUT_NO_MECHANICS"


def test_boot_timeout():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=30,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="loading",
        visual_response=False,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=True,
    )
    assert r.code == "BOOT_TIMEOUT"


def test_success_returns_none():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=True,
        mechanics_verified_count=2,
        menu_status="gameplay_entered",
        visual_response=True,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r is None


def test_all_codes_have_ar_labels():
    for code in FAILURE_CODES:
        r = classify_runtime_failure_for_code_smoke(code)
        assert r.reason_ar
```

(Add helper `classify_runtime_failure_for_code_smoke` in test file or parametrize.)

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_godot_failure_taxonomy.py -v`  
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement taxonomy**

```python
# app/godot_runtime/failure_taxonomy.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

FAILURE_CODES = (
    "BOOT_TIMEOUT",
    "BLACK_SCREEN_PERSISTENT",
    "MENU_NOT_RESOLVED",
    "WINDOW_NOT_FOUND",
    "NO_VISUAL_RESPONSE_TO_INPUT",
    "SERVER_DEPENDENCY_BLOCK",
    "PROCESS_CRASHED",
    "GAMEPLAY_ENTERED_BUT_NO_MECHANICS",
)

_LABELS_AR: Dict[str, str] = {
    "BOOT_TIMEOUT": "انتهت مهلة الإقلاع — الشاشة لم تنتقل من التحميل/السواد.",
    "BLACK_SCREEN_PERSISTENT": "شاشة سوداء مستمرة بعد polling كامل.",
    "MENU_NOT_RESOLVED": "قائمة/start screen لم تُحل إلى gameplay.",
    "WINDOW_NOT_FOUND": "تعذّر العثور على نافذة اللعبة أو التقاطها.",
    "NO_VISUAL_RESPONSE_TO_INPUT": "لا استجابة بصرية للإدخال بعد burst التفاعل.",
    "SERVER_DEPENDENCY_BLOCK": "حوار شبكة/خادم يمنع اللعب (Connection Failed).",
    "PROCESS_CRASHED": "عملية اللعبة انتهت أثناء المراقبة.",
    "GAMEPLAY_ENTERED_BUT_NO_MECHANICS": "دخل gameplay لكن لم تُثبت أي ميكانيكا.",
}


@dataclass(frozen=True)
class GodotRuntimeFailure:
    code: str
    reason_ar: str
    reason_en: str
    evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
    evidence = {
        "window_detected": window_detected,
        "black_screen_duration_s": black_screen_duration_s,
        "gameplay_entered": gameplay_entered,
        "mechanics_verified_count": mechanics_verified_count,
        "menu_status": menu_status,
        "visual_response": visual_response,
        "server_dialog_detected": server_dialog_detected,
        "process_crashed": process_crashed,
        "boot_timed_out": boot_timed_out,
    }
    if gameplay_entered and mechanics_verified_count >= 1:
        return None
    if process_crashed:
        return _fail("PROCESS_CRASHED", evidence)
    if server_dialog_detected:
        return _fail("SERVER_DEPENDENCY_BLOCK", evidence)
    if not window_detected:
        return _fail("WINDOW_NOT_FOUND", evidence)
    if gameplay_entered and mechanics_verified_count == 0:
        return _fail("GAMEPLAY_ENTERED_BUT_NO_MECHANICS", evidence)
    if boot_timed_out:
        return _fail("BOOT_TIMEOUT", evidence)
    if black_screen_duration_s >= 20:
        return _fail("BLACK_SCREEN_PERSISTENT", evidence)
    status = (menu_status or "").lower()
    if status in ("menu", "loading", "unknown") and not gameplay_entered:
        if "menu" in status:
            return _fail("MENU_NOT_RESOLVED", evidence)
        if boot_timed_out or black_screen_duration_s > 10:
            return _fail("BOOT_TIMEOUT", evidence)
        return _fail("BLACK_SCREEN_PERSISTENT", evidence)
    if gameplay_entered is False and not visual_response:
        return _fail("NO_VISUAL_RESPONSE_TO_INPUT", evidence)
    if not gameplay_entered:
        return _fail("MENU_NOT_RESOLVED", evidence)
    return None


def _fail(code: str, evidence: Dict[str, Any]) -> GodotRuntimeFailure:
    return GodotRuntimeFailure(
        code=code,
        reason_ar=_LABELS_AR[code],
        reason_en=code.replace("_", " ").lower(),
        evidence=evidence,
    )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_godot_failure_taxonomy.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/godot_runtime/ tests/test_godot_failure_taxonomy.py
git commit -m "feat(godot): add runtime failure taxonomy"
```

---

### Task 2: Godot retry policy

**Files:**
- Create: `app/godot_runtime/retry_policy.py`
- Modify: `app/gameplay_verifier.py` (~1145)
- Create: `tests/test_godot_retry_policy.py`

- [ ] **Step 1: Write failing test** — mock `MenuNavigator` / `PlaytestOrchestrator`; assert `retry_attempts` length ≥ 2 when first nav fails.

- [ ] **Step 2: Implement `GodotRetryPolicy.run()`**

Sequence:
1. nav pass #1
2. playtest #1
3. if not `gameplay_entered`: refocus + nav pass #2 + playtest #2
4. `classify_runtime_failure()` → attach to return dict

Return shape extends existing `run_automated_gameplay_verification` report:

```python
{
  ...existing keys...,
  "failure_reason_code": "MENU_NOT_RESOLVED" | None,
  "failure_reason_ar": "...",
  "godot_retry_attempts": [{"step": "nav_pass_1", ...}, ...],
}
```

- [ ] **Step 3: Wire in `run_automated_gameplay_verification`**

Replace inline single-retry with:

```python
from app.godot_runtime.retry_policy import is_godot_runtime_path, run_godot_automated_verification

if is_godot_runtime_path(artifact_path):
    return run_godot_automated_verification(...)
# else existing path
```

- [ ] **Step 4: Regression tests**

Run: `pytest tests/test_godot_retry_policy.py tests/test_menu_navigator.py tests/test_pro_gameplay_verification.py -v`

- [ ] **Step 5: Commit**

---

### Task 3: Attach taxonomy to sandbox + OCR server detect

**Files:**
- Modify: `app/runtime_observation_sandbox.py` (~739)
- Modify: `app/gameplay_verifier.py` (`_shot_ocr_text` / menu flow)

- [ ] **Step 1: Detect server dialog** — OCR keywords: `connection failed`, `failed to connect`, `server`, `network`.

- [ ] **Step 2: Pass flags into classifier** at end of Godot observation.

- [ ] **Step 3: Test** — unit test with mocked OCR snippet → `SERVER_DEPENDENCY_BLOCK`.

- [ ] **Step 4: Commit**

---

### Task 4: Soak test runner

**Files:**
- Create: `scripts/godot_soak_test.py`

- [ ] **Step 1: Implement runner**

For each fixture in `godot_soak_fixtures.json`:
- Run runtime-only or lightweight grade path (prefer direct sandbox call for speed if available).
- Collect required fields per run.
- Write `reports/godot_soak_YYYYMMDD_HHMMSS.json`.

Exit 0 iff:
- ≥ 8/9 runs **correct** (Pass when gameplay entered; classified failure otherwise)
- submission 50: 3 runs same outcome class (all P or all same `failure_reason_code`)
- every failed run has non-null `failure_reason_code`

Run: `python scripts/godot_soak_test.py --runs 3`  
Expected: JSON report path printed.

- [ ] **Step 2: Commit**

---

### Task 5: Word / UI contract

**Files:**
- Modify: `app/report_feedback_formatter.py`
- Modify: `app/gameplay_verifier.py` (`format_agent_play_summary_ar`)
- Modify: `app/templates/batch_results.html`

- [ ] **Step 1: Word** — append `failure_reason_ar` when code set; never raw JSON.

- [ ] **Step 2: Agent play summary** — use taxonomy label; no `L4 جزئي` when `gameplay_entered=false`.

- [ ] **Step 3: UI badge** — show `failure_reason_code` in runtime evidence row.

- [ ] **Step 4: Manual spot-check** on one Pass + one classified-fail snapshot.

- [ ] **Step 5: Commit**

---

### Task 6: Soak execution + sign-off

- [ ] **Step 1:** `python scripts/discover_godot_soak_fixtures.py`
- [ ] **Step 2:** `python scripts/godot_soak_test.py --runs 3`
- [ ] **Step 3:** Fix flakes until DoD §9 (spec) passes
- [ ] **Step 4:** Fill sign-off table in `godot-closeout-checklist.md`
- [ ] **Step 5:** Commit checklist + soak report path

---

## Plan self-review

| Spec requirement | Task |
|------------------|------|
| 8 failure codes | Task 1 |
| Godot-only retry | Task 2 |
| Soak matrix C + per-run fields | Task 0, 4 |
| Word/UI contract | Task 5 |
| DoD sign-off | Task 6 |
| B.P3/B.P4 untouched | Regression in Task 2, 4 |
| No false L4 without gameplay | Task 1 test + Task 5 |

**Gap:** Second student fixture may be `pending` until upload — documented in Task 0; DoD B requires resolution.

---

## Execution handoff

Plan saved. Recommended: **Inline execution** in current session (Tasks 0→1→2→3→4→5→6 sequentially with verification gates).
