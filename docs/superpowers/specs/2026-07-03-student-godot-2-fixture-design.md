# Student Godot #2 — Soak Fixture Selection & Onboarding

**Date:** 2026-07-03  
**Status:** Approved — option C (dual trial, pick winner); trial runner approved  
**Parent:** `2026-07-03-godot-runtime-closeout-design.md` (Strategy C, §16)  
**Depends on:** `9fbf57e` Godot runtime baseline (capture stability + soak harness v2)  
**Blocks:** Godot Closeout DoD **B** — cannot sign off until `student_godot_2_stable=true`

---

## 1. Problem

Soak matrix Strategy C requires **three fixtures × 3 runs**:

| Fixture | Role | Status (2026-07-03) |
|---------|------|---------------------|
| `submission_50` | Real student — menu + loading (`P_03.exe`) | **Stable** — 3× P |
| `corpus_l1_godot_export_001` | Calibration regression | **Stable** — 3× `PROCESS_CRASHED` |
| `student_godot_2` | Second real student — complementary path | **Blocked** — no exe on disk; harness `student_folder` kind not wired |

Only one student `.exe` exists locally (`uploads/students/bx72/.../P_03.exe`). A second student project is **ready to upload** (option A). Without fixture #2, Godot cannot be declared **Closed (engine-level)** even though submission_50 and corpus are stable.

**Harness gap:** `scripts/godot_soak_test.py` treats `kind: student_folder` as `unsupported` when `pending: false`. Fixture registration alone is insufficient — soak must run the exe via `observe_runtime_artifacts`.

---

## 2. Goal

1. Select and register a **second real student Godot exe** that complements submission_50 coverage.
2. Prefer **direct gameplay** (boot → gameplay without complex menu navigation).
3. Run soak `--runs 3` with **stable, honest** outcomes (3× P or 3× same `failure_reason_code`).
4. Extend soak evaluation so **`student_godot_2_stable`** gates Godot closeout alongside `submission_50_stable`.

---

## 3. Fixture role in the matrix

```
submission_50     → complex menu + loading + full GodotRetryPolicy path
corpus_l1         → deterministic crash regression (calibration)
student_godot_2   → direct gameplay OR simple menu (student production)
```

**Why direct gameplay is preferred:** submission_50 already exercises `nav_pass_*` → `play_pass_*`. Fixture #2 should prove Godot runtime on a **different entry path** — immediate gameplay after boot — with lower flake surface (no menu OCR/clicks).

**Acceptable fallback:** simple single-screen menu (e.g. one “Play” button) if no direct gameplay project is available, provided a manual trial shows nav resolves in ≤2 attempts.

---

## 4. Selection criteria (hard gates)

A candidate exe **must** pass all gates before registration in `godot_soak_fixtures.json`:

| # | Gate | Rule |
|---|------|------|
| G1 | Not submission_50 | Path must not resolve to `P_03.exe` / submission id 50 |
| G2 | Godot evidence | Parent folder contains `*.gd` and/or `project.godot` |
| G3 | No network dependency | Reject if path/name contains `connection`, `network`, `server`, `login`, `multiplayer` |
| G4 | Runtime budget | Single trial run completes observation in **< 60 s** (target 30–45 s for direct gameplay) |
| G5 | Honest outcome | Trial yields either `gameplay_entered=true` or a single `failure_reason_code` — never empty gv |
| G6 | No flip on repeat | Two manual trials (same session) produce the same grade/code class |

**Reject** candidates that flip P ↔ U without code change, or depend on external services.

### Scoring (discover script — optional ranking)

When multiple candidates exist, rank by:

1. `+20` — no `.gd` menu scene name containing `main_menu`, `title`, `start` **and** gameplay scene loads at boot (heuristic: first screenshot shows playable HUD/sprite)
2. `+10` — Godot folder (`*.gd` / `project.godot`)
3. `+5` — exe name not matching submission_50
4. `−10` — path hints network/server

Manual override in `godot_soak_fixtures.json` always wins over auto-discover.

---

## 5. Fixture JSON schema

```json
{
  "id": "student_godot_2",
  "kind": "student_folder",
  "path": "uploads/students/<batch>/<folder>/<Game>.exe",
  "profile": "direct_gameplay",
  "expected_behavior": "stable_pass",
  "submission_id": null,
  "pending": false,
  "notes": "Second student Godot — direct gameplay; registered YYYY-MM-DD"
}
```

| Field | Values | Notes |
|-------|--------|-------|
| `profile` | `direct_gameplay` \| `simple_menu` | Set after trial |
| `expected_behavior` | `stable_pass` \| `stable_failure` | `stable_failure` when trial shows consistent U + code |
| `submission_id` | int or null | Optional; enables future `full_grade` mode — **not required** for closeout soak |
| `pending` | false when path set and gates pass | true → soak skips with documented reason |

---

## 6. Onboarding workflow

### Step 0 — Upload

Place the student export under:

```
uploads/students/<batch>/<student_folder>/<Game>.exe
```

Include Godot source alongside exe if available (`*.gd`, `project.godot`) for gate G2.

### Step 1 — Copy hamtini exports (option C)

Copy both candidates into soak discover path (exe + matching `.pck` in same folder):

```
ai_grader_python/uploads/students/hamtini_u8/farst game.exe
ai_grader_python/uploads/students/hamtini_u8/farst game.pck
ai_grader_python/uploads/students/hamtini_u8/final.exe
ai_grader_python/uploads/students/hamtini_u8/final.pck
```

Source: `uploads/تجربة/New folder/ahmad hamtini u8 part2/.exe/`

### Step 2 — Dual trial (mandatory before fixture lock)

Run **`scripts/godot_trial_runner.py`** once per exe (see §6.1). Compare reports; pick winner per §14.7.

### Step 3 — Discover or manual path

```powershell
cd ai_grader_python
python scripts/discover_godot_soak_fixtures.py
```

Review output; edit `path` manually to the **winning** exe if discover picks wrong file.

### Step 4 — Register fixture

Set `pending: false`, `path`, `profile`, `expected_behavior`, and `notes` (why this exe won) in `godot_soak_fixtures.json`.

### Step 5 — Soak matrix

```powershell
python scripts/godot_soak_test.py --runs 3
```

### Step 6 — Evaluate stability

`student_godot_2_stable = true` when all 3 runs match **either**:

- **Pass pattern:** `grade_level=P`, `gameplay_entered=true`, `failure_reason_code=null`
- **Failure pattern:** same non-empty `failure_reason_code` on all 3 runs, `gameplay_entered` not true

Plus matrix-wide: `blocking_bug_count=0`, no `failed_without_failure_code`, `correct_runs ≥ 8/9`.

---

## 6.1 Godot trial runner (`scripts/godot_trial_runner.py`)

**Purpose:** One-shot PRO runtime observation for a candidate exe **before** registering in `godot_soak_fixtures.json`. Avoids full soak (~9 runs) on rejected builds.

**CLI:**

```powershell
python scripts/godot_trial_runner.py --exe "uploads/students/hamtini_u8/farst game.exe"
python scripts/godot_trial_runner.py --exe "uploads/students/hamtini_u8/final.exe"
python scripts/godot_trial_runner.py --compare reports/godot_trial_farst.json reports/godot_trial_final.json
```

**Behavior:**

1. Resolve exe path relative to `ai_grader_python/` ROOT.
2. Verify sibling `.pck` exists (warn if missing).
3. Call `observe_runtime_artifacts([exe], grading_mode="deep", enable_smoke_test=True)`.
4. Extract via `resolve_authoritative_gameplay_verification` (same truth path as soak).
5. Emit JSON report to stdout and `reports/godot_trial_<slug>_<timestamp>.json`.

**Report fields (minimum):**

```json
{
  "exe_path": "uploads/students/hamtini_u8/farst game.exe",
  "student_label": "ahmad hamtini",
  "duration_ms": 42000,
  "launch_ok": true,
  "gameplay_entered": true,
  "failure_reason_code": null,
  "l4_level": "L4_partial",
  "screenshot_count": 12,
  "godot_retry_steps": ["play_pass_1"],
  "profile_guess": "direct_gameplay",
  "network_hints": false,
  "gates_passed": true,
  "notes": []
}
```

**`--compare` mode:** Read two trial JSON files; rank by:

1. `gates_passed` (gv honest, bool gameplay_entered)
2. Stability signals: fewer errors in `interaction_trace`, `capture_pipeline` absent
3. `profile_guess`: prefer `direct_gameplay` over `simple_menu` when tied
4. Shorter `duration_ms` when outcomes equal
5. Tie-break: prefer **`final.exe`** if both stable (closer to real student deliverable)

Print recommended `path` + `profile` for `godot_soak_fixtures.json`.

**Not in scope:** Full AI grade, DB submission, repeated runs (soak handles 3×).

---

## 6.2 Legacy inline trial (fallback)

If trial runner not yet implemented, one-liner:

```powershell
python -c "..."  # see git history §6 Step 2
```

Prefer trial runner once shipped.

---

## 7. Harness changes (required)

### 7.1 Wire `student_folder` kind

In `scripts/godot_soak_test.py`, when `kind == "student_folder"` and not `pending`:

```python
def _run_student_folder_fixture(fixture: dict) -> dict:
    exe = ROOT / str(fixture["path"])
    if not exe.is_file():
        raise FileNotFoundError(f"student exe missing: {exe}")
    return observe_runtime_artifacts(
        [str(exe)],
        grading_mode="deep",
        enable_smoke_test=True,
    )
```

Use `_observation_run_record` (same as `corpus_exe`) — runtime-only soak, no full AI grade unless `submission_id` is added later.

### 7.2 Evaluation: `student_godot_2_stable`

Mirror `submission_50_stable` logic:

- Collect runs where `fixture_id == "student_godot_2"` and not skipped.
- Apply same `all_pass` / `all_same_fail` stability rule.
- Add to evaluation payload:

```json
{
  "submission_50_stable": true,
  "student_godot_2_stable": true,
  "passed": true
}
```

**Closeout gate:** `passed` requires **both** `submission_50_stable` and `student_godot_2_stable` when fixture is not pending.

### 7.3 Discover script enhancement (minor)

Prefer direct-gameplay candidates:

- Skip submission_50 exe explicitly (already implemented).
- Boost score when folder has gameplay `.gd` without heavy menu scenes.
- Write `profile` hint into fixture notes.

---

## 8. Expected outcomes

### Primary target (direct gameplay student)

| Field | Expected |
|-------|----------|
| `gameplay_entered` | `true` (3/3) |
| `l4_level` | `L4_partial` or higher |
| `failure_reason_code` | `null` |
| `grade_level` | `P` (runtime_only: derived from gv, not full grade) |
| Screenshots | 8–16 (shorter than submission_50 if no nav passes) |
| `godot_retry_attempts` | May show `play_pass_1` only (no `nav_pass_*`) |

### Acceptable alternative (stable failure)

| Field | Expected |
|-------|----------|
| `failure_reason_code` | Same code 3/3 (e.g. `PROCESS_CRASHED`, `WINDOW_NOT_FOUND`) |
| `gameplay_entered` | `false` 3/3 |

**Not acceptable:** mix of P and U; `NO_VISUAL_RESPONSE_TO_INPUT` on capture-preflight-only runs (3 screenshots); empty `gameplay_verification`.

---

## 9. Touch matrix

| Zone | Files |
|------|-------|
| **GREEN** | `scripts/godot_trial_runner.py`, `scripts/godot_soak_test.py`, `scripts/discover_godot_soak_fixtures.py`, `scripts/godot_soak_fixtures.json`, `tests/test_godot_trial_runner.py`, `tests/test_godot_orchestrator_wiring.py` |
| **RED** | No changes to `GodotRetryPolicy`, capture tuning, BTEC governance, deterministic engine |

Fixture onboarding is harness-only unless trial exposes a new runtime bug (then separate bugfix spec).

---

## 10. Testing

| Test | Assert |
|------|--------|
| `test_godot_trial_runner.py` | Trial report shape + compare ranking |
| `test_student_folder_fixture_runs_when_path_set` | Mock `observe_runtime_artifacts`; `student_folder` not skipped |
| `test_student_godot_2_stable_pass_pattern` | 3× P → `student_godot_2_stable=true` |
| `test_student_godot_2_stable_failure_pattern` | 3× same code → stable |
| `test_evaluate_matrix_requires_student_godot_2` | `passed=false` when sub50 stable but student_godot_2 unstable |
| `test_discover_skips_submission_50` | Only one exe on disk → pending stays true |

Integration: manual soak after upload (not CI per closeout §14).

---

## 11. Definition of Done (this spec)

- [ ] Student exe uploaded under `uploads/students/...`
- [ ] Gates G1–G6 pass on trial run
- [ ] `godot_soak_fixtures.json` updated (`pending: false`)
- [ ] Harness wires `student_folder` kind
- [ ] `student_godot_2_stable` in evaluation
- [ ] Soak `--runs 3` → 9 active runs, ≥8/9 correct, both student fixtures stable
- [ ] `godot-closeout-checklist.md` updated — DoD B checked

---

## 12. Out of scope

- Full `db_submission` grade for student_godot_2 (optional later via `submission_id`)
- Synthetic calibration fixture as permanent replacement (Strategy C requires real student #2)
- Unity / GameMaker engines
- Changes to `CAPTURE_PROBE_MAX_ATTEMPTS` or retry policy tuning

---

## 13. Self-review

- [x] No TBD in gates or stability definition
- [x] Harness gap (`student_folder` unsupported) documented and scoped
- [x] Consistent with Strategy C and closeout DoD B
- [x] Direct gameplay preference explicit; simple menu fallback documented
- [x] Single implementation plan scope (harness + fixture registration)
- [x] Discovery inventory from `uploads/تجربة` documented (§14)

---

## 14. Discovery inventory — `uploads/تجربة` (2026-07-03)

Workspace path: `d:\cchat\aaaa\ai_grader_python (2)\uploads\تجربة`  
(Note: outside `ai_grader_python/uploads/students/` — fixture must be **copied or linked** into soak discover path.)

### 14.1 Godot exports found

| Student | Path | Size | Gate G1 | Notes |
|---------|------|------|---------|-------|
| **ahmad hamtini** (U8) | `New folder/ahmad hamtini u8 part2/.exe/farst game.exe` | ~90 MB | **Pass** | `.pck` alongside; **only non–Ahmad-Bakr Godot export ready** |
| **ahmad hamtini** (U8) | `.../.exe/final.exe` | ~90 MB | **Pass** | Same folder; likely later iteration |
| Ahmad Bakr (submission_50) | `P_03.exe`, `العبة قبل/بعد التعديل/.../P_03.exe` | ~96–99 MB | **Fail G1** | Same student as fixture #1 |
| محمد عضيبات | `GAME B&C/.../new-game-project/` | — | N/A | **Source only** — `main_menu.gd` (Play → gameplay); **no `.exe` export** |
| محمد عكاوي | `اللعبه ماريو/...` | — | N/A | **Unity** (`kong-tutorial`), not Godot |

### 14.2 Non-Godot (excluded)

| Folder | Engine |
|--------|--------|
| CAT RUNNER عمر صبري | Unity |
| حسين السلامات Kitten Run | Unity |
| عبدالله العتوم | Unity |
| Jana Dwiri CheeseChase | Unknown (~7.6 MB, no Godot markers) |
| عبدارحمن بني مصطفى / ريان الشوبكي / سموور | GameMaker (`.yyp`) |

### 14.3 Candidate pair (option C — approved)

Trial **both**, register **one** winner in `godot_soak_fixtures.json`.

| Build | Path (after copy) | Role |
|-------|-------------------|------|
| Early | `uploads/students/hamtini_u8/farst game.exe` | May be simpler; fewer polish bugs |
| Final | `uploads/students/hamtini_u8/final.exe` | May be richer UI; tie-break if both stable |

### 14.7 Winner selection (post-trial)

| Priority | Criterion |
|----------|-----------|
| 1 | **Gates G4–G6** — runtime < 60s, honest gv, no flip on second manual trial |
| 2 | **Stability** — clear P or single failure code; no capture mislabel |
| 3 | **Profile value** — `direct_gameplay` > `simple_menu` > complex menu |
| 4 | **Pedagogy** — if tied on stability, prefer **`final.exe`** |

Document choice in fixture `notes`, e.g.  
`"Selected final.exe — both trials passed; final has HUD + stable play_pass_1 only."`

### 14.8 Fallback if both hamtini builds fail gates

1. Export محمد عضيبات `new-game-project` (simple menu).
2. Document blocker in checklist if no stable second student remains.

### 14.5 Explicitly rejected for fixture #2

- Any `P_03.exe` / Ahmad Bakr folder — fails **G1** (same student as `submission_50`).
- Unity / GameMaker projects — wrong engine for Godot closeout.
- محمد عكاوي Mario — Unity.

### 14.6 Open item (trial run)

Before locking fixture JSON, run **one** `observe_runtime_artifacts` trial on `farst game.exe` and record:

- `gameplay_entered`, `failure_reason_code`, screenshot count, wall time
- Whether `godot_retry_attempts` includes `nav_pass_*` or skips to `play_pass_*`

This determines `profile`: `direct_gameplay` vs `simple_menu`.
