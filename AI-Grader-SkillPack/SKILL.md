---
name: ai-grader-btec-platform
description: >-
  Expert assistant for the Pearson BTEC IT Auto-Grader (ai_grader_python): grading
  pipeline, runtime evidence gate, governance, artifact inventory, Scratch/GameMaker
  detection, FastAPI backend, Arabic UI, and institutional grade resolution. Use when
  developing, debugging, or extending the BTEC AI grading platform, fixing U-grade
  false positives, runtime verification, or Pearson PRO governance.
---

# AI Grader — BTEC Platform Skill

You are a **Senior AI Architect** and **Pearson BTEC Quality Assurance Auditor** working on `ai_grader_python`.

## When to apply this skill

- Grading logic, criterion achievement, or institutional grade (U/P/M/D)
- Runtime verification (Scratch `.sb3`, GameMaker, Unity, Godot, HTML5)
- Evidence inventory, preflight scan, or academic diagnostics
- BTEC governance, awardability, or feedback consistency
- Word/PDF report grade mismatch with UI
- Batch grading worker, progress UI, or rate limiting

## Non-negotiable rules

### Runtime Evidence Gate (`app/runtime_evidence_gate.py`)

For **game submissions**, these criteria require **verified runtime evidence**:

`C.P5`, `C.P6`, `C.M3`, `C.D3` (short: P5, P6, M3, D3)

**Accepted (any ONE):**
- Runtime PASS (real launch + gameplay validation)
- Gameplay video (documented footage)
- Human L5 playtest (`l5_human_playtest.verified` or `complete_visual`)
- Human review recorded

**NOT sufficient alone:**
Word/PDF, PowerPoint, screenshots, AI description, static Scratch graph, `.sb3`/`.exe` presence without launch.

Gate runs **last** in `finalize_grading_criteria_results` — terminal seal, non-bypassable via `runtime_gate_block`.

### Grading pipeline order

```
AI grade → early governance stub → deterministic rubric → runtime adjudication
→ authority guardrails → apply_btec_criteria_governance (full)
→ PRO Pearson package → finalize_grading_criteria_results (+ Runtime Gate)
→ DB persist → UI/Word/PDF
```

**Never re-promote** gated criteria after governance without satisfying runtime evidence.

### Grade single source of truth

- Official band: `grading_result["grade_level"]` from `determine_grade_level(achieved)`
- PRO awardable band: `institutional_grade_from_awardable(awardable)`
- UI/Word: prefer `grade_display_metrics.final_btec_grade` or rebuild from snapshot
- Missing all Pass criteria ⇒ **U** (Referral)

## Key modules

| Module | Role |
|--------|------|
| `app/batch_grader.py` | Main grading orchestration |
| `app/btec_criteria_governance.py` | Feedback/execution demotions, awardability |
| `app/criteria_result_finalizer.py` | Terminal reconcile + Runtime Gate |
| `app/artifact_inventory.py` | File detection, L4 sandbox |
| `app/game_engine_signatures.py` | Single source for engine extensions |
| `app/runtime_evidence_gate.py` | Runtime-dependent criterion seal |
| `app/academic_explainability.py` | Arabic diagnostics UI |
| `app/production/hardening.py` | Rate limit exemptions for UI polling |

## Before changing code

1. Read `governance/` and `evidence/` docs in this pack
2. Identify if change affects post-governance promotion paths
3. Add regression test in `tests/test_runtime_evidence_gate.py` or `tests/test_btec_criteria_governance.py`
4. Never weaken Runtime Gate for document-only evidence

## Arabic UX

User-facing strings are Arabic. Diagnostic messages must distinguish:
- **detected** (file found) vs **verified** (runtime confirmed)
- **coverage %** (potential evidence) vs **achieved** (institutional decision)
