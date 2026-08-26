# Deterministic B.P3 / B.P4 Rules — Design Spec

**Date:** 2026-07-03  
**Status:** Approved — Implemented (B.P3/B.P4); Godot runtime closeout tracked separately in `2026-07-03-godot-runtime-closeout-design.md`  
**Path:** `docs/superpowers/specs/2026-07-03-deterministic-bp3-bp4-design.md`  
**Depends on:** `2026-07-02-pro-gameplay-verification-design.md` (runtime/Gate layer — complete)

---

## 1. Context & Motivation

### 1.1 Problem Statement

For submission 50 (Ahmad Bakr) and similar game projects, **runtime and Gate are now correct**:

- `gameplay_entered = true`, `L4_partial`, C.P5/C.P6 Gate open in PRO.
- Grade remains **U** because **AI text grading is non-deterministic** on design criteria.

| Symptom | Root cause (code audit) |
|---------|-------------------------|
| B.P3 flips between Pass/Fail across regrades | `evaluate_criterion_deterministic` uses `student_text` only; Word extract can be **~132 chars** while full corpus is **17k+** |
| B.P4 mapped to wrong rule | `deterministic_engine.py` treats `B.P4` like **peer review / survey** (`questionnaire_or_survey`), but assignment 3 defines B.P4 as **إنتاج تصميمات بصرية أساسية** |
| AI overrides unstable | `merge_deterministic_with_ai` enforces deterministic result in strict mode — but current B.P3/B.P4 rules **fail** on thin text, so AI `achieved=False` wins |

### 1.2 Goal

Make **B.P3** and **B.P4** decisions **reproducible** from structural evidence (documents, GDD sections, vision, source artifacts). LLM becomes **explainer only** for these two criteria in PRO mode.

### 1.3 Non-Goals

- Do not change C.P5/C.P6/M3/D3 Gate policy (handled by `runtime_evidence_gate.py`).
- Do not remove AI grading globally — only **seal** B.P3/B.P4 when deterministic evidence threshold is met.
- Do not loosen STANDARD mode: structural rules apply in PRO; STANDARD may keep lighter hints (see §4.3).

---

## 2. Design Options Considered

### Option A — Extend `deterministic_engine.py` inline (minimal)

Add richer regex + `artifact_inventory` reads inside existing `evaluate_criterion_deterministic`.

| Pros | Cons |
|------|------|
| Smallest diff | File already large; B.P4 branch is semantically wrong and hard to untangle |
| Fast | Mixes Pearson game design with generic peer-review heuristics |

### Option B — New `design_evidence_assessor.py` + thin wiring (recommended)

Dedicated module builds a **DesignEvidenceBundle** from registry/inventory, returns `CriterionDecision` for B.P3/B.P4. `deterministic_engine` delegates for those levels only.

| Pros | Cons |
|------|------|
| Clear boundary; testable pure functions | One new file + wiring |
| Fixes B.P4 mis-mapping without risking C.P4 elsewhere | |
| Reuses `evidence_registry`, `visual_evidence_registry`, `artifact_inventory` | |

### Option C — Post-AI governance overlay only

Let AI grade, then promote B.P3/B.P4 if coverage % high.

| Pros | Cons |
|------|------|
| No rubric changes | Still depends on AI variance before overlay; not truly deterministic |

**Recommendation:** **Option B.**

---

## 3. Architecture

### 3.1 Flow (PRO)

```
artifact_inventory + student_text + vision_summary
        ↓
DesignEvidenceAssessor.build_bundle()
        ↓
evaluate_bp3_deterministic(bundle) → CriterionDecision
evaluate_bp4_deterministic(bundle) → CriterionDecision
        ↓
deterministic_engine.evaluate_criterion_deterministic()
  (delegates when criteria_level ∈ {B.P3, B.P4})
        ↓
merge_deterministic_with_ai (strict → enforced)
        ↓
finalize_grading_criteria_results / btec_criteria_governance
```

### 3.2 `DesignEvidenceBundle` (dataclass)

| Field | Source |
|-------|--------|
| `design_doc_present` | `documentation.status`, Word/PDF in `artifact_inventory.documentation` |
| `design_doc_signals` | Regex on **full grading corpus** (student_text + code addon + extracted doc text), not primary path only |
| `gdd_sections` | Snippets matching mechanics / levels / HUD / UI / controls (AR+EN) |
| `ui_screenshot_count` | `embedded_screenshots`, `visual_verification`, vision registry |
| `wireframe_or_mockup_count` | Vision labels + image filenames (mockup, wireframe, UI, واجهة) |
| `source_scenes_present` | `.tscn`, UI nodes in `.gd`, GameMaker/Godot hints |
| `survey_present` | `testing_evidence`, questionnaire/survey tokens in corpus |
| `test_section_present` | `test_plan`, `functional_test`, مرحلة الاختبار, bug log |
| `embedded_image_count` | From Word extract debug (e.g. 20 images) |

### 3.3 B.P3 Rule — `design_evidence_rule_v1`

**Criterion (assignment 3):** إنتاج تصميمات فنية أساسية لألعاب الحاسوب.

**Scoring (0–3 signals, need ≥2 for Pass):**

| Signal | Detection |
|--------|-----------|
| S1 — Design document | `design_doc_present` AND corpus mentions GDD/تصميم/character/asset/شخصية |
| S2 — Game structure | GDD or corpus covers ≥2 of: `mechanics`, `levels`, `HUD`, `controls`, `game flow` |
| S3 — Visual artefact | `ui_screenshot_count + wireframe_or_mockup_count ≥ 1` OR ≥3 embedded images with design context |

```python
achieved = score >= 2
deterministic_score = 70 if achieved else 35
authority = "DESIGN_EVIDENCE_RULE_V1"
```

### 3.4 B.P4 Rule — `visual_design_rule_v1`

**Criterion (assignment 3):** إنتاج تصميمات بصرية أساسية لألعاب الحاسوب.

**Important:** Remove conflation with **C.P4 peer review**. `B.P4` uses this rule; `C.P4` keeps existing peer-review logic.

> **In PRO mode, B.P4 is a foundational visual-design pass criterion, not a presentation-quality or peer-review criterion; therefore a single verified visual-design signal is sufficient for deterministic Pass.**

**Scoring (0–2 signals, need ≥1 for Pass in PRO):**

| Signal | Detection |
|--------|-----------|
| V1 — UI / screen designs | Vision or embedded images showing menu/HUD/game screen OR corpus mentions واجهة/شاشة/أزرار/UI layout |
| V2 — Testing / user-feedback doc | `survey_present` OR `test_section_present` (استبيان واحد يكفي في PRO) |

```python
achieved = score >= 1
deterministic_score = 70 if achieved else 35
authority = "VISUAL_DESIGN_RULE_V1"
```

### 3.5 AI Role After Seal

When `deterministic_achieved=True` and `authority` is design rule:

- `achieved` / `awardable` / `score` come from deterministic decision (strict merge).
- LLM `feedback` may be **rewritten or appended** via optional `explain_bp3_pass(bundle)` — narrative only, no flip.
- Store `ai_proposed_achieved` when AI disagreed (audit trail).

When `deterministic_achieved=False`:

- AI may still Fail or mark Partial.
- Deterministic `evidence_registry` lists **which signals were missing** for teacher transparency.

### 3.6 Corpus Construction (fixes 132-char bug)

`DesignEvidenceAssessor` MUST use `build_grading_corpus(grading_result)` (or equivalent already used for AI prompt):

- Primary submission text
- Code addon (`CODE-ADDON` path in batch_grader)
- Document extraction aggregate
- **Not** `submission_file_path` basename only

Minimum corpus length guard: if corpus `< 500` chars but `embedded_image_count ≥ 5`, still evaluate from inventory + vision flags.

---

## 4. Mode Policy

| Mode | B.P3/B.P4 behavior |
|------|-------------------|
| **PRO** (`deep`/`pro`) | Full structural rules; strict merge **enforces** Pass when thresholds met |
| **STANDARD** (`fast`) | Same rules but `verdict_status=inconclusive` when runtime/docs thin; do not auto-fail if ≥2 signals |

Gate interaction: B.P3/B.P4 are **not** runtime-gated. B.M2 prerequisite on B.P3/B.P4 unchanged in `btec_criteria_governance.py`.

---

## 5. Files to Touch

| File | Change |
|------|--------|
| `app/design_evidence_assessor.py` | **New** — bundle + `evaluate_bp3_deterministic` + `evaluate_bp4_deterministic` |
| `app/rubric/deterministic_engine.py` | Delegate B.P3/B.P4; fix `B.P4` branch mis-route |
| `app/batch_grader.py` | Pass full corpus / inventory into `run_deterministic_rubric` if not already |
| `tests/test_design_evidence_assessor.py` | **New** — unit tests per rule |
| `tests/test_pro_gameplay_verification.py` | Integration: Ahmad-like bundle → B.P3/B.P4 Pass |

---

## 6. Test Plan

### 6.1 Unit

- `test_bp3_passes_with_gdd_and_ui_screens` — score≥2 → achieved
- `test_bp3_fails_with_exe_only` — no doc/vision → not achieved
- `test_bp4_passes_with_survey_only` — Ahmad case (استبيان + partial testing_evidence)
- `test_bp4_not_peer_review_rule` — B.P4 does not use `text_has_design_peer_evidence` alone
- `test_c_p4_still_peer_review` — regression: C.P4 path unchanged

### 6.2 Integration

- Regrade submission 50: expect B.P3/B.P4 `achieved=True` stable across 2 consecutive runs.
- With C.P5/C.P6 Gate open → `grade_level` at least **P**.

---

## 7. Success Criteria

1. Two consecutive PRO regrades of submission 50 produce **identical** `achieved` for B.P3 and B.P4.
2. Ahmad bundle (GDD + 20 embedded images + survey + Godot source) yields B.P3 Pass, B.P4 Pass without AI agreement.
3. No regression: STANDARD C.P4 peer review tests still pass.
4. Word/UI report shows `achievement_authority=DESIGN_EVIDENCE_RULE_V1` or `VISUAL_DESIGN_RULE_V1` when sealed.

---

## 8. Rollout Order

1. Implement `design_evidence_assessor.py` + tests.
2. Wire into `deterministic_engine.py` (fix B.P4 mapping).
3. Verify corpus includes full document extract.
4. Regrade submission 50 twice; confirm **P** minimum.
5. Optional: AI explainer-only feedback polish (no grade impact).

---

## 9. Open Questions

1. **B.P4 threshold:** Is `≥1` visual OR survey signal sufficient, or require **both** for Merit-bound projects? (Current spec: ≥1 — matches Ahmad case.)
2. **C.P6 narrative:** Gate open but AI fails on "no presentation" — separate spec for C.P6 deterministic presentation detection? **Out of scope** for this spec unless user expands.
