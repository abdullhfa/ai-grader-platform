# Student Godot #2 Fixture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register `student_godot_2` (ahmad hamtini) after dual trial, wire soak harness `student_folder` kind, and pass 9-run soak matrix for Godot closeout DoD B.

**Architecture:** Copy hamtini exports → `godot_trial_runner.py` observes each exe once and `--compare` picks winner → update `godot_soak_fixtures.json` → extend `godot_soak_test.py` with `student_folder` + `student_godot_2_stable` gate → full soak `--runs 3`.

**Tech Stack:** Python 3.11+, pytest, `observe_runtime_artifacts`, `resolve_authoritative_gameplay_verification`, existing soak harness v2.

**Spec:** `docs/superpowers/specs/2026-07-03-student-godot-2-fixture-design.md` (commit `fffc348`)

---

## File map

| File | Responsibility |
|------|----------------|
| `uploads/students/hamtini_u8/farst game.exe` | Trial candidate A (+ `.pck`) |
| `uploads/students/hamtini_u8/final.exe` | Trial candidate B (+ `.pck`) |
| `scripts/godot_trial_runner.py` | Single-exe trial + `--compare` |
| `scripts/godot_soak_test.py` | Wire `student_folder`; `student_godot_2_stable` |
| `scripts/godot_soak_fixtures.json` | Winner path + profile |
| `scripts/discover_godot_soak_fixtures.py` | Prefer hamtini over P_03 |
| `tests/test_godot_trial_runner.py` | Report + compare unit tests |
| `tests/test_godot_orchestrator_wiring.py` | Soak `student_folder` + stability eval |
| `docs/superpowers/specs/godot-closeout-checklist.md` | Check DoD B after soak |

---

### Task 1: Copy hamtini exports

**Files:**
- Create: `uploads/students/hamtini_u8/farst game.exe`
- Create: `uploads/students/hamtini_u8/farst game.pck`
- Create: `uploads/students/hamtini_u8/final.exe`
- Create: `uploads/students/hamtini_u8/final.pck`

- [ ] **Step 1: Create destination folder**

```powershell
cd "d:\cchat\aaaa\ai_grader_python (2)\ai_grader_python"
New-Item -ItemType Directory -Force -Path "uploads\students\hamtini_u8"
```

- [ ] **Step 2: Copy from workspace تجربة**

```powershell
$src = "d:\cchat\aaaa\ai_grader_python (2)\uploads\تجربة\New folder\ahmad hamtini u8 part2\.exe"
Copy-Item "$src\farst game.exe" "uploads\students\hamtini_u8\"
Copy-Item "$src\farst game.pck" "uploads\students\hamtini_u8\"
Copy-Item "$src\final.exe" "uploads\students\hamtini_u8\"
Copy-Item "$src\final.pck" "uploads\students\hamtini_u8\"
```

- [ ] **Step 3: Verify**

```powershell
Get-ChildItem "uploads\students\hamtini_u8" | Select-Object Name, Length
```

Expected: 4 files; each exe ~90 MB.

**Note:** Do not commit large binaries unless repo policy allows — document path in fixture JSON only if `.gitignore` excludes `uploads/students/hamtini_u8/`.

---

### Task 2: Godot trial runner

**Files:**
- Create: `scripts/godot_trial_runner.py`
- Create: `tests/test_godot_trial_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_godot_trial_runner.py
from scripts.godot_trial_runner import build_trial_report, compare_trial_reports


def test_build_trial_report_from_observation():
    obs = {
        "runtime_observed": True,
        "runtime_screenshots": [{"status": "captured"}] * 10,
        "gameplay_verification": {
            "gameplay_entered": True,
            "l4_level": "L4_partial",
            "godot_retry_attempts": [{"step": "play_pass_1"}],
        },
        "interaction_trace": {"errors": []},
    }
    report = build_trial_report(
        obs,
        exe_path="uploads/students/hamtini_u8/final.exe",
        duration_ms=35000,
    )
    assert report["gates_passed"] is True
    assert report["gameplay_entered"] is True
    assert report["profile_guess"] == "direct_gameplay"


def test_compare_prefers_final_on_tie():
    farst = {
        "exe_path": "uploads/students/hamtini_u8/farst game.exe",
        "gates_passed": True,
        "gameplay_entered": True,
        "failure_reason_code": None,
        "profile_guess": "direct_gameplay",
        "duration_ms": 40000,
    }
    final = {**farst, "exe_path": "uploads/students/hamtini_u8/final.exe", "duration_ms": 38000}
    winner = compare_trial_reports([farst, final])
    assert "final.exe" in winner["exe_path"]
```

- [ ] **Step 2: Run tests — expect FAIL**

```powershell
python -m pytest tests/test_godot_trial_runner.py -v
```

- [ ] **Step 3: Implement `scripts/godot_trial_runner.py`**

Core functions:

```python
def _slug_from_exe(exe_path: str) -> str: ...
def _guess_profile(gv: dict, steps: list) -> str:
    # nav_pass in steps -> simple_menu; only play_pass -> direct_gameplay

def build_trial_report(obs: dict, *, exe_path: str, duration_ms: int) -> dict: ...

def compare_trial_reports(reports: list[dict]) -> dict: ...

def run_trial(exe: Path) -> dict:
    from app.runtime_observation_sandbox import observe_runtime_artifacts
    from app.gameplay_verifier import resolve_authoritative_gameplay_verification
    t0 = time.monotonic()
    obs = observe_runtime_artifacts([str(exe)], grading_mode="deep", enable_smoke_test=True)
    gv = resolve_authoritative_gameplay_verification(artifact_inventory={}, grading_result={"gameplay_verification": obs.get("gameplay_verification")})
    if gv:
        obs["gameplay_verification"] = gv
    return build_trial_report(obs, exe_path=str(exe.relative_to(ROOT)), duration_ms=int((time.monotonic()-t0)*1000))
```

CLI: `--exe PATH` | `--compare FILE FILE` | `--out reports/...`

- [ ] **Step 4: Run tests — expect PASS**

```powershell
python -m pytest tests/test_godot_trial_runner.py -v
```

---

### Task 3: Dual trial + pick winner

**Files:**
- Create: `reports/godot_trial_farst.json` (generated)
- Create: `reports/godot_trial_final.json` (generated)

- [ ] **Step 1: Trial farst**

```powershell
python scripts/godot_trial_runner.py --exe "uploads/students/hamtini_u8/farst game.exe" --out reports/godot_trial_farst.json
```

- [ ] **Step 2: Trial final**

```powershell
python scripts/godot_trial_runner.py --exe "uploads/students/hamtini_u8/final.exe" --out reports/godot_trial_final.json
```

- [ ] **Step 3: Compare**

```powershell
python scripts/godot_trial_runner.py --compare reports/godot_trial_farst.json reports/godot_trial_final.json
```

Record winner `exe_path`, `profile_guess`, and rationale in plan notes / fixture `notes`.

**Gate:** Both trials must have `gates_passed=true` OR one stable failure code. If both fail gates, stop and document blocker (spec §14.8).

---

### Task 4: Wire soak `student_folder` + stability eval

**Files:**
- Modify: `scripts/godot_soak_test.py`
- Modify: `tests/test_godot_orchestrator_wiring.py`

- [ ] **Step 1: Add `_run_student_folder_fixture`**

Mirror `_run_corpus_fixture` — resolve `ROOT / fixture["path"]`, call `observe_runtime_artifacts`.

- [ ] **Step 2: Branch in `run_matrix`**

```python
elif kind == "student_folder":
    obs = _run_student_folder_fixture(fixture)
    record = _observation_run_record(obs, fixture_id=fid, run_index=i, duration_ms=...)
```

- [ ] **Step 3: Track `student_godot_2_runs` like `submission_50_runs`**

Extend `_evaluate_matrix`:

```python
def _fixture_stable(runs: list[dict]) -> bool:
    if len(runs) < 3:
        return False
    grades = {str(r.get("grade_level") or "") for r in runs}
    codes = {str(r.get("failure_reason_code") or "") for r in runs}
    all_pass = grades == {"P"} and all(r.get("gameplay_entered") is True for r in runs)
    all_same_fail = len(codes) == 1 and codes != {""} and all(r.get("gameplay_entered") is not True for r in runs)
    return all_pass or all_same_fail
```

Add `student_godot_2_stable` to evaluation; `passed` requires both sub50 and student_godot_2 stable when fixture not pending.

- [ ] **Step 4: Tests**

```python
def test_student_folder_kind_not_skipped(monkeypatch, tmp_path):
    # mock observe_runtime_artifacts; assert kind student_folder produces runtime_only record

def test_evaluate_matrix_requires_student_godot_2_stable():
    # sub50 stable + student_godot_2 unstable -> passed false
```

- [ ] **Step 5: Run tests**

```powershell
python -m pytest tests/test_godot_orchestrator_wiring.py tests/test_godot_trial_runner.py -v
```

---

### Task 5: Register fixture JSON

**Files:**
- Modify: `scripts/godot_soak_fixtures.json`
- Modify: `scripts/discover_godot_soak_fixtures.py` (optional: score hamtini paths)

- [ ] **Step 1: Update `student_godot_2` entry**

```json
{
  "id": "student_godot_2",
  "kind": "student_folder",
  "path": "uploads/students/hamtini_u8/<WINNER>.exe",
  "profile": "direct_gameplay",
  "expected_behavior": "stable_pass",
  "pending": false,
  "notes": "ahmad hamtini U8 — selected <WINNER> after dual trial (see reports/godot_trial_*.json)"
}
```

Replace `<WINNER>` with compare output.

- [ ] **Step 2: Run discover (sanity)**

```powershell
python scripts/discover_godot_soak_fixtures.py
```

Confirm path not overwritten to P_03.

---

### Task 6: Full soak + closeout checklist

**Files:**
- Create: `reports/godot_soak_<timestamp>.json`
- Modify: `docs/superpowers/specs/godot-closeout-checklist.md`

- [ ] **Step 1: Run soak**

```powershell
python scripts/godot_soak_test.py --runs 3
```

Expected (~15–20 min):
- `submission_50_stable`: true
- `student_godot_2_stable`: true
- `blocking_bug_count`: 0
- `passed`: true
- 9 active runs (3 fixtures × 3)

- [ ] **Step 2: Verify report vs snapshots**

No `NO_VISUAL_RESPONSE_TO_INPUT` on capture-only failures for student_godot_2.

- [ ] **Step 3: Update checklist**

Check DoD A + B rows; add soak report path and commit hash to sign-off table.

- [ ] **Step 4: graphify update**

```powershell
graphify update .
```

- [ ] **Step 5: Commit implementation**

Message: `Godot closeout: student_godot_2 fixture via trial runner and soak harness`

---

## Spec coverage checklist

| Spec section | Task |
|--------------|------|
| §6 copy hamtini | Task 1 |
| §6.1 trial runner | Task 2 |
| §6 Step 2 dual trial | Task 3 |
| §7 harness student_folder | Task 4 |
| §7.2 student_godot_2_stable | Task 4 |
| §5 fixture JSON | Task 5 |
| §11 DoD | Task 6 |
| §14.7 winner selection | Task 3 |

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-07-03-student-godot-2-fixture.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — execute tasks in this session with checkpoints

Which approach?
