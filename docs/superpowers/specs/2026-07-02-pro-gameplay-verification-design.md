# PRO Gameplay Verification Design Spec

**Date:** 2026-07-02  
**Status:** Draft — Approved for Implementation  
**Path:** `docs/superpowers/specs/2026-07-02-pro-gameplay-verification-design.md`

---

## 1. Context & Motivation

### 1.1 Problem Statement

The current PRO grading pipeline for executable games (Godot, Unity, GameMaker) suffers from three categories of failure:

| Category | Description | Impact |
|----------|-------------|--------|
| **False positives** | `player_movement_verified=true` even when `gameplay_entered=false` | Gate opens on menu-screen pixel delta |
| **Retroactive evidence** | `requirement_checklist` built after grading, not driving it | Evidence not linked to specific BTEC criteria |
| **Misleading UI** | `desktop_fallback` screenshots shown as gameplay evidence | Teacher/student trust eroded |

### 1.2 Design Decision: Gate Policy (Option C)

| Criteria | Gate Policy | Rationale |
|----------|-------------|-----------|
| **C.P5** | Automatic (L4_partial+) | Objective: prototype runs + ≥1 mechanic verified |
| **C.P6** | Automatic (L4_partial+ + test docs) | Objective: test doc present + run evidence |
| **C.M3** | Teacher confirmation required | Qualitative: improvement quality not machine-measurable |
| **C.D3** | Teacher confirmation required | Qualitative: full loop + reflection depth |

---

## 2. Architecture Overview

### 2.1 New PRO Flow

```
Brief / GDD / Test Plan
        ↓
RequirementExtractor
        ↓
RequirementPlan (list of RequirementTest objects)
        ↓
GameLauncher + MenuNavigator
        ↓
   gameplay_entered?
     /         \
   NO           YES
   ↓             ↓
L3 evidence   PlaytestOrchestrator
              (iterates RequirementPlan)
                    ↓
              for each RequirementTest:
                input_sequence → before_screenshot
                                → execute_input
                                → after_screenshot
                                → verify(CV/OCR)
                    ↓
              EvidencePackage
              (req_id + btec_criterion + result + screenshots)
                    ↓
              BTECCriterionMapper
                    ↓
              GateDecision (per criterion)
```

### 2.2 Core Invariants (Non-Negotiable)

1. **`player_movement_verified` requires `gameplay_entered == True`** — enforced at verification layer, not caller
2. **Every screenshot tagged**: `capture_scope=game_window`, `requirement_id`, `phase=before|after`
3. **`jump_observed` only from vertical pixel shift** — never inferred from movement proxy
4. **`desktop_fallback` screenshots rejected in PRO mode** — raise `EvidenceQualityError`
5. **Gate decision logged immutably** with full evidence chain

---

## 3. Component Specifications

### 3.1 `RequirementExtractor`

**File:** `app/requirement_extractor.py`

**Purpose:** Parse Brief, GDD, Test Plan documents to produce a structured `RequirementPlan`.

```python
@dataclass
class RequirementTest:
    req_id: str                    # e.g. "player_movement"
    description: str               # e.g. "Player moves left/right"
    btec_criteria: list[str]       # e.g. ["C.P5", "C.M3"]
    input_sequence: list[InputAction]  # ordered actions to test
    verification_method: str       # "pixel_shift" | "ocr" | "object_detection"
    success_threshold: float       # minimum confidence to mark verified
    required_for_gate: bool        # if True, Gate blocked on failure

@dataclass
class RequirementPlan:
    submission_id: str
    engine: str                    # "godot" | "unity" | "gamemaker" | "exe"
    requirements: list[RequirementTest]
    extracted_from: list[str]      # source document paths
    extraction_confidence: float
```

**Default plan when no GDD available:** see `DEFAULT_GODOT_EXE_PLAN` in `app/requirement_extractor.py`.

---

### 3.2 `MenuNavigator` (Revised)

**File:** `app/gameplay_verifier.py` — class `MenuNavigator`

Revised navigation with visual state classifier (`gameplay` | `menu` | `loading` | `unknown`), OCR play-button detection, and `gameplay_entered` result.

---

### 3.3 `PlaytestOrchestrator`

**File:** `app/gameplay_verifier.py`

Iterates `RequirementPlan`, skips non-menu tests when `gameplay_entered` is false, tags screenshots with `requirement_id` and `phase`, raises `EvidenceQualityError` on `desktop_fallback` in PRO.

---

### 3.4 `RequirementVerifier`

Pixel shift (horizontal/vertical), OCR HUD change, scene change (SSIM) — vertical shift exclusively for jump.

---

### 3.5 `BTECCriterionMapper` + Gate Logic

**File:** `app/runtime_evidence_gate.py`

Gate rules for C.P5 (automatic), C.P6 (automatic + test docs), C.M3/C.D3 (teacher confirmation).

---

### 3.6 L4 Level Calculation

`calculate_l4_level(evidence)` — L3 / L4_partial / L4_full based on `gameplay_entered` and verified mechanic count.

---

## 4. Evidence Display — UI & Word Report

Screenshot slots: `req_{id}_before`, `req_{id}_after`, `menu_nav_entry`.  
UI table: requirement → input → screenshot → result → BTEC criterion.  
Agent play label with per-mechanic status.

---

## 5. Integration — `runtime_observation_sandbox.py`

PRO flow: extract plan → launch → menu navigate → playtest → BTEC map → package.

---

## 6. Test Plan

### 6.1 Unit Tests (10 required)

| Test | Validates |
|------|-----------|
| `test_movement_requires_gameplay_entered` | INVARIANT #1 |
| `test_desktop_fallback_rejected_in_pro` | INVARIANT #4 |
| `test_jump_not_proxy_from_movement` | INVARIANT #3 |
| `test_gate_cp5_opens_on_l4_partial` | Gate policy — automatic |
| `test_gate_cp6_requires_test_doc_2_entries` | Pearson C.P6 min entries |
| `test_gate_cm3_requires_teacher_confirmation` | Gate policy — teacher |
| `test_gate_cd3_requires_teacher_confirmation` | Gate policy — teacher |
| `test_l4_level_calculation_all_cases` | L3 / L4_partial / L4_full |
| `test_requirement_extractor_default_plan` | Default Godot plan |
| `test_evidence_package_screenshot_tags` | Screenshot metadata |

### 6.2 Integration Test — Submission 50 (Ahmad Bakr)

Expected: `gameplay_entered=true`, L4_partial+, C.P5/C.P6 gate open, C.M3/C.D3 teacher confirmation, grade P minimum.

---

## 7. Implementation Order (Cursor Tasks)

| # | Task | File |
|---|------|------|
| 1 | `RequirementExtractor` + `DEFAULT_GODOT_EXE_PLAN` | `app/requirement_extractor.py` (new) |
| 2 | `MenuNavigator` rewrite | `app/gameplay_verifier.py` |
| 3 | `PlaytestOrchestrator` + `RequirementVerifier` | `app/gameplay_verifier.py` |
| 4 | `BTECCriterionMapper` + `GateRule` | `app/runtime_evidence_gate.py` |
| 5 | `calculate_l4_level()` | `app/gameplay_verifier.py` |
| 6 | PRO flow integration | `app/runtime_observation_sandbox.py` |
| 7 | New fields in `GradingProfile` | `app/core/grading_profiles.py` |
| 8 | Word/PDF evidence table | `app/academic_explainability.py` |
| 9 | UI evidence table + L4 label | `app/templates/` |
| 10 | All 10 unit tests + integration test | `tests/` |

---

## 8. Acceptance Criteria

- [ ] `player_movement_verified=true` impossible without `gameplay_entered=true`
- [ ] No `desktop_fallback` screenshot in PRO mode evidence
- [ ] `jump_observed` only from vertical pixel shift
- [ ] C.P5 Gate opens automatically on L4_partial
- [ ] C.P6 Gate opens automatically on L4_partial + ≥2 test doc entries
- [ ] C.M3 and C.D3 always require teacher confirmation
- [ ] Word report shows requirement table with before/after screenshots
- [ ] Submission 50 grades P or higher without human intervention
- [ ] All 10 unit tests pass
- [ ] Integration test matches §6.2

---

*Document owner: AI Grader Platform Engineering*  
*Next review: after Task 10 completion*
