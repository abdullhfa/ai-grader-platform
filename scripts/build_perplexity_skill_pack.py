"""Build AI-Grader-SkillPack.zip for Perplexity Spaces upload."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "AI-Grader-SkillPack"
ZIP_OUT = Path(__file__).resolve().parents[1] / "AI-Grader-SkillPack.zip"
ZIP_PERPLEXITY = Path(__file__).resolve().parents[1] / "AI-Grader-SkillPack-Perplexity.zip"

FILES: dict[str, str] = {}

# ── Root ──────────────────────────────────────────────────────────────────────

FILES["README.md"] = """# AI-Grader Skill Pack (Pearson BTEC)

Professional knowledge pack for the **BTEC IT Auto-Grader** (`ai_grader_python`).

## Purpose

This pack teaches an AI assistant how to work on a Pearson-grade BTEC grading platform:
architecture, governance, evidence, runtime verification, AI reasoning, reports, and security.

## Repository

- GitHub: `https://github.com/abdullhfa/ai-teacher`
- Stack: Python 3.11+, FastAPI, SQLite, Gemini (Flash/Pro), Jinja2 UI

## Golden Rules

1. **Runtime before award** — C.P5/C.P6/C.M3/C.D3 require real runtime/playtest evidence.
2. **Governance is final** — `finalize_grading_criteria_results` + Runtime Evidence Gate seal decisions.
3. **Single source of truth** — `grade_level` + `criteria_results[].achieved/awardable` everywhere.
4. **Never commit secrets** — `.env`, student uploads, DB files stay out of git.

## Folder Index

| Folder | Focus |
|--------|-------|
| `architecture/` | System design, folders, patterns, workflow |
| `governance/` | BTEC authority, award rules, human review |
| `evidence/` | Inventory, registry, confidence, coverage |
| `runtime/` | Engine sandboxes, Scratch/GM/Unity/Godot |
| `ai/` | LLM grading, prompting, hallucination control |
| `pearson/` | Pass/Merit/Distinction BTEC rules |
| `reports/` | Word/PDF/UI grade rendering |
| `backend/` | FastAPI, services, DB, API |
| `frontend/` | Templates, dashboard, JS |
| `security/` | Upload validation, sandbox, auth |
| `testing/` | pytest, governance regression |
| `prompts/` | Debugging, review, refactor prompts |
"""

FILES["SKILL.md"] = """---
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
"""

FILES["LICENSE.md"] = """# License

Copyright (c) 2026 Eng. Abdullah / BTEC Teachers Platform.

This skill pack documents the **ai_grader_python** project architecture and governance.
Use within educational and institutional grading contexts.

The underlying application code is proprietary unless otherwise stated on GitHub.
"""

FILES["CHANGELOG.md"] = """# Changelog — AI-Grader Skill Pack

## v1.0.0 (2026-06-29)

- Initial professional Perplexity Skill Pack release
- Runtime Evidence Gate documentation (C.P5/C.P6/C.M3/C.D3)
- Scratch `.sb3` detection and governance path-fallback fixes
- Bug Log removed from mandatory preflight (optional bonus)
- Batch UI redirect fix (finished flag before PDF generation)
- GitHub repository: abdullhfa/ai-teacher
"""

# ── architecture/ ─────────────────────────────────────────────────────────────

FILES["architecture/system_architecture.md"] = """# System Architecture

## Overview

Layered FastAPI application for automated Pearson BTEC IT assignment grading.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Web UI     │────▶│  main.py     │────▶│  batch_grader   │
│  (Jinja2)   │     │  FastAPI     │     │  grade_batch    │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
     ┌─────────────────────────────────────────────┼──────────────────┐
     ▼                     ▼                       ▼                  ▼
 artifact_inventory   Gemini AI            deterministic_rubric   runtime/sandbox
     │                     │                       │                  │
     └─────────────────────┴───────────────────────┴──────────────────┘
                                    │
                          btec_criteria_governance
                                    │
                          criteria_result_finalizer
                          (+ runtime_evidence_gate)
                                    │
                          SQLite (submissions, batches)
```

## Execution modes

| Mode | Key | Behavior |
|------|-----|----------|
| BASIC | `fast` | Skips heavy runtime, advisory only |
| PRO | `deep` | Full L4 sandbox, Vision, gameplay video |

## Data flow

1. Upload → archive extract → `submission_paths`
2. Preflight scan → advisory grade hint
3. Text + image extraction → `student_text`, vision
4. AI structured JSON → `criteria_results`
5. Deterministic merge → governance → finalizer seal
6. Snapshot JSON → `Submission.grading_snapshot_json`
"""

FILES["architecture/folder_structure.md"] = """# Folder Structure

```
ai_grader_python/
├── main.py                 # FastAPI app, routes, Word export
├── run_dev_server.py       # Dev server (port 5557)
├── app/
│   ├── batch_grader.py     # Core grading pipeline
│   ├── batch_grade_worker.py
│   ├── btec_criteria_governance.py
│   ├── criteria_result_finalizer.py
│   ├── runtime_evidence_gate.py
│   ├── artifact_inventory.py
│   ├── game_engine_signatures.py
│   ├── academic_explainability.py
│   ├── rubric/deterministic_engine.py
│   ├── runtime/            # L4 sandbox orchestrator
│   ├── runtime_engines/    # scratch, gamemaker, godot, web
│   ├── production/hardening.py
│   ├── templates/          # Arabic HTML UI
│   └── routes/grading.py
├── tests/
├── uploads/                # Runtime only (gitignored: students/)
└── scripts/
```

## Do not edit casually

- `game_engine_signatures.py` — single source for `.sb3`, `.yyp`, etc.
- `btec_grade_resolution.py` — institutional band logic
- `finalize_grading_criteria_results` — terminal seal location
"""

FILES["architecture/design_patterns.md"] = """# Design Patterns

## Pipeline + Terminal Seal

Grading uses sequential enrichment layers. The **terminal seal** (`finalize_grading_criteria_results` → Runtime Gate) runs last and cannot be bypassed by earlier promotions.

## Single Source of Truth

- Engine signatures: `game_engine_signatures.py`
- Grade band: `determine_grade_level()` on `achieved`
- Award band (PRO): `institutional_grade_from_awardable()` on `awardable`

## Advisory vs Authority

| Layer | Authority level |
|-------|-----------------|
| Preflight scan | Advisory hint only |
| Vision L3 | Advisory visual inference |
| L4 sandbox | Partial runtime observation |
| L5 human playtest | Governed human review |
| Governance + Gate | **Institutional decision** |

## Hold flags

- `pro_gameplay_governance_hold` — blocks finalizer re-promotion (PRO)
- `runtime_gate_block` — blocks all re-promotion for gated criteria

## Idempotent governance

`apply_runtime_evidence_gate` is safe to call on every snapshot reload (results page, Word export).
"""

FILES["architecture/dependency_graph.md"] = """# Dependency Graph (grading path)

```
grade_batch_async
  └─ grade_single_student
       ├─ grade_student_submission (AI)
       │    └─ apply_btec_criteria_governance [EARLY STUB - no inventory]
       └─ _finalize_grading_result_after_ai
            ├─ run_deterministic_rubric
            ├─ apply_runtime_criterion_adjudication
            ├─ apply_criterion_authority_guardrails
            ├─ apply_btec_criteria_governance [FULL]
            ├─ apply_pro_pearson_btec_package
            └─ finalize_grading_criteria_results
                 ├─ reconcile_authoritative_achieved
                 ├─ apply_deliverable_game_criteria_pass
                 └─ apply_runtime_evidence_gate  ← TERMINAL
batch_grade_worker
  └─ finalize_grading_criteria_results (again)
  └─ DB commit + PDF
```

## Bypass risks (fixed)

- Early governance without inventory → false "no project files" demotion
- Finalizer promoting P5/P6 after governance → blocked by `runtime_gate_block`
- UI reading stale `institutional_resolution` → cache invalidated on gate demotion
"""

FILES["architecture/coding_workflow.md"] = """# Coding Workflow

## Setup

```bash
cd ai_grader_python
python -m venv .venv
.venv\\Scripts\\activate   # Windows
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY, SECRET_KEY
python run_dev_server.py    # http://localhost:5557
```

## Change checklist

1. Identify pipeline stage affected (see dependency_graph.md)
2. Minimize diff — one concern per commit
3. Run targeted tests:
   ```bash
   python -m pytest tests/test_runtime_evidence_gate.py tests/test_btec_criteria_governance.py -q
   ```
4. Restart dev server after backend changes
5. Never commit `.env` or `uploads/students/`

## Branch naming

`fix/runtime-gate-scratch`, `feat/preflight-v4`, `docs/skill-pack`
"""

# ── governance/ ───────────────────────────────────────────────────────────────

FILES["governance/governance_rules.md"] = """# BTEC Governance Rules

Module: `app/btec_criteria_governance.py`

## Functions (order inside `apply_btec_criteria_governance`)

1. `enforce_feedback_achieved_consistency` — demote if feedback contradicts achieved=True
2. `enforce_execution_artifact_requirements` — P5/P6/P7/M3 need game artifacts (informative inventory only)
3. `apply_btec_awardability` — set `awardable` per cumulative BTEC rules
4. `enforce_not_achieved_feedback_consistency` — align feedback when achieved=False
5. `sanitize_all_criteria_feedback` — strip governance prefixes

## Cumulative awardability

- All Pass criteria `achieved` → eligible for P
- All Pass + all Merit `achieved` → eligible for M
- All Pass + Merit + Distinction `achieved` → eligible for D
- Any mandatory Pass missing → **U** (even if Merit achieved)

## Early vs full governance

Early stub (in `grade_student_submission`) runs **without** artifact inventory — must NOT demote on empty inventory (`_has_informative_artifact_signal` guard).
"""

FILES["governance/authority_rules.md"] = """# Authority Rules

## Achievement authority values

| Value | Meaning |
|-------|---------|
| `DETERMINISTIC_DOCUMENTARY` | Text/doc evidence path |
| `RUNTIME_OBSERVATION_L4` | Automated sandbox observation |
| `HUMAN_PLAYTEST_L5` | Teacher verified playtest |
| `RUNTIME_GATE_BLOCKED` | Terminal gate demotion |
| `RUNTIME_INSUFFICIENT` | Partial runtime, not awardable |
| `HUMAN_REVIEW_REQUIRED` | Needs L5 before award |

## Evidence ladder (L0–L5)

- L0: no runtime evidence
- L1: executable detected (artifact acknowledgment)
- L2: screenshot candidates (advisory)
- L3: gameplay video (advisory inference)
- L4: runtime observed (partial)
- L5: human verified replay (never auto-assigned)

## Rule

Higher authority cannot be claimed from lower-level evidence alone.
"""

FILES["governance/award_validation.md"] = """# Award Validation

## Two orthogonal fields

| Field | Drives |
|-------|--------|
| `achieved` | Academic verification — did student meet criterion? |
| `awardable` | Institutional grant — can BTEC band include this criterion? |

Example: B.M2 `achieved=True` but `awardable=False` when C.P6 Pass is missing (cumulative block).

## Runtime-gated criteria

`RUNTIME_GATED_SHORT = {P5, P6, M3, D3}`

Cannot be `achieved=True` for game submissions without:
- Runtime PASS, OR gameplay video, OR L5 playtest

## Validation tests

- `tests/test_btec_criteria_governance.py`
- `tests/test_runtime_evidence_gate.py`
- `tests/test_criteria_result_finalizer.py`
"""

FILES["governance/mandatory_evidence.md"] = """# Mandatory Evidence

## By criterion type (Unit 8 Games — typical)

| Criterion | Mandatory evidence |
|-----------|---------------------|
| B.P3 | GDD — audience, art style, asset table |
| B.P4 | Visual designs, flowchart, storyboards |
| C.P5 | Runnable prototype + **runtime verification** |
| C.P6 | Testing/communication + **playtest or video** |
| B.M2 | Peer review notes, GDD v2 |
| C.M3 | Refinement evidence + **runtime** |
| B.D2 / C.D3 | Advanced design + **runtime** |

## NOT mandatory (optional bonus)

- Bug Log — removed from preflight mandatory checks (v4)
- Test Plan filename — may be embedded in Word document

## File presence ≠ verification

`.sb3` detected → diagnostic says "Scratch موجود" but `present` may be False until runtime verified.
"""

FILES["governance/human_review.md"] = """# Human Review (L5)

## Triggers

- GameMaker PRO: automated gameplay loop unreliable
- Runtime partial / structure-only analysis
- `achievement_authority = HUMAN_REVIEW_REQUIRED`

## L5 fields

```python
l5_human_playtest.status == "complete_visual"
l5_human_playtest.verified == True
runtime_observation_report.human_playtest_verified == True
```

## Policy

L5 satisfies Runtime Evidence Gate for C.P6/M3/D3.
L4 alone does **not** substitute L5 for GameMaker PRO playtest-gated criteria.

## UI

Human moderation templates: `human_moderation.html`, playtest merge via `submission_playtest.py`.
"""

# ── evidence/ ─────────────────────────────────────────────────────────────────

FILES["evidence/evidence_engine.md"] = """# Evidence Engine

## Pipeline

1. **Preflight** (`preflight_evidence_scan.py`) — fast filename/path scan
2. **Artifact inventory** (`artifact_inventory.py`) — full file catalog
3. **Evidence completeness gate** (`evidence_completeness_gate.py`) — per-criterion assets
4. **Evidence strength** (`evidence_strength.py`) — confidence 0..1
5. **Coverage score** (`evidence_coverage_score.py`) — weighted % per criterion

## Golden rule

Coverage % = potential evidence in files — **does not mean criterion achieved**.
UI must show disclaimer: refer to «معايير BTEC — تحقق / منح» for institutional decision.
"""

FILES["evidence/evidence_registry.md"] = """# Evidence Registry

Module: `app/evidence_registry.py`

## `build_grade_display_metrics()`

Single display hub for official grade:

```python
inst_btec = institutional_resolution.btec_grade or grade_level
final_btec_grade = inst_btec_short
```

## On Runtime Gate demotion

Invalidate stale caches:
- `institutional_resolution`
- `grade_display_metrics`
- `btec_institutional_award`
- `expected_runtime_grade`

Forces UI/Word/PDF to rebuild from gated `grade_level`.
"""

FILES["evidence/evidence_mapping.md"] = """# Evidence Mapping

## Criterion → evidence types

| Short | Primary evidence |
|-------|------------------|
| P3/P4 | Word/PDF design docs |
| P5 | Executable/source + runtime |
| P6 | Test docs + presentation + runtime/playtest |
| M2 | Reviewer feedback records |
| M3/D2/D3 | Refinement + runtime |

## Engine → artifact keys

| Engine | Signatures |
|--------|------------|
| Scratch | `.sb3`, `.sb2` |
| GameMaker | `.yyp`, `.gml`, `data.win` |
| Godot | `project.godot`, `.pck`, `.gd` |
| Unity | `Assets/`, `.unity` |
| HTML5 | `index.html` + wasm/js |

Central module: `app/game_engine_signatures.py`
"""

FILES["evidence/confidence.md"] = """# Evidence Confidence

## Layers

| Module | Output |
|--------|--------|
| `evidence_strength.py` | `decision_confidence` 0..1 |
| `ai/reliability_layer.py` | AI disagreement risk |
| `evidence_completeness_gate.py` | `has_gaps`, demotion hints |

## Weak source demotion

`weak_src` when extraction coverage < 50% — does **not** apply to Scratch projects (`.sb3` is self-contained source).

## Diagnostic confidence

Arabic diagnostics in `academic_explainability.py` separate:
- file **detected** vs **verified**
- advisory vs institutional authority
"""

FILES["evidence/coverage.md"] = """# Evidence Coverage

Module: `app/evidence_coverage_score.py` (v2.6)

## C.P6 weighted model

| Component | Weight |
|-----------|--------|
| test_plan | 45% |
| presentation | 25% |
| survey/feedback | 25% |
| bug_log | 10% (optional bonus) |

Bug Log is **not** mandatory — optional bonus only.

## UI colors

- Green ≥ 70% — high potential coverage
- Yellow 40–69% — partial
- Red < 40% — weak

Coverage does not override Runtime Gate or governance.
"""

# ── runtime/ (abbreviated but complete) ───────────────────────────────────────

for eng, body in {
    "runtime_engine.md": """# Runtime Engine

## Entry points

- `app/runtime/sandbox_engine.py` → `run_sandbox_observation`
- `app/runtime/orchestrator.py` — multi-engine dispatch
- `app/runtime/validation_engine.py` — `functional_smoke_pass`

## Status values

`completed`, `partial`, `failed`, `skipped`, `gated`, `timeout`, `crashed`

## `runtime_verified` strict definition (PRO)

```python
launch_ok and smoke_ok and not crash and not structure_only
```

Structure-only (Scratch static graph, Godot static scan) → **never** counts as PASS.
""",
    "scratch_runtime.md": """# Scratch Runtime

- Extensions: `.sb3`, `.sb2` (see `game_engine_signatures.py`)
- BASIC: `scratch_static_graph` — parses project JSON, **no VM**
- PRO: `scratch_pro_runtime_verification` — graph + optional VM
- Static graph alone → `runtime_verified = False`
- Inventory: classified as `executable` + `source` (`artifact_kind: scratch_project`)
""",
    "python_runtime.md": """# Python Runtime

- Detection: `.py` files in submission
- Sandbox: compile check + optional subprocess smoke
- Used for non-game Python assignments (not primary games unit path)
""",
    "unity_runtime.md": """# Unity Runtime

- Markers: `Assets/`, `ProjectSettings/`, `.unity`
- Build: `.exe` in Build folder
- Special case: `unity_runtime_observed` may set observed but not verified without smoke
- Playmode tests supported in PRO policy
""",
    "godot_runtime.md": """# Godot Runtime

- Markers: `project.godot`, `.gd`, `.pck`
- `godot_static_analysis` → status `partial`, `runtime_verified=False`
- Real launch requires `.exe` or engine invocation with smoke pass
""",
    "html_runtime.md": """# HTML5 Runtime

- Detection: `index.html` + wasm/js bundles
- Web automation via Playwright (`runtime_engines/web/`)
- Screenshot capture for L4 observation
""",
    "gamemaker_runtime.md": """# GameMaker Runtime

- Markers: `.yyp`, `.gml`, `.yy`, `data.win`
- PRO: `human_review_required=True` in engine policy
- Automated L4 may launch `.exe` but gameplay loop detection is unreliable
- C.P6/M3/D2/D3 prefer L5 playtest or documented gameplay video
""",
}.items():
    FILES[f"runtime/{eng}"] = body

# ── ai/ ───────────────────────────────────────────────────────────────────────

FILES["ai/ai_reasoning.md"] = """# AI Reasoning

- Provider: Gemini via `app/ai_provider.py`
- Models: `gemini-2.5-flash` (fast), `gemini-2.5-pro` (deep/PRO)
- Structured JSON output per criterion
- `HybridGrader.merge_results` — rule overlay on AI verdict
- `ai_evidence_reasoning` — institutional sufficiency decision
"""

FILES["ai/llm_rules.md"] = """# LLM Rules

1. Never trust AI `achieved=True` without governance pass
2. Include model + prompt version in grading cache fingerprint (determinism)
3. AI feedback stripped of governance prefixes before teacher display
4. Contradictory feedback (claims success + denial) → governance demotion
5. Document-only path cannot award runtime-dependent criteria
"""

FILES["ai/hallucination.md"] = """# Hallucination Control

## Risks

- AI claims "تم تحقيق المعيار" when evidence is documentary only
- AI invents Bug Log / Test Plan requirements not in assignment brief
- AI confuses coverage % with achieved status

## Mitigations

- Deterministic rubric merge (`deterministic_engine.py`)
- `enforce_feedback_achieved_consistency`
- Runtime Evidence Gate terminal seal
- `evidence_strength` confidence scoring
- Arabic diagnostics with authority labels
"""

FILES["ai/prompting.md"] = """# Prompting

- Criterion-by-criterion evaluation in single PRO call
- Reference solution + student text + vision context
- Arabic feedback required for teacher UI
- Do not include mandatory Bug Log in C.P6 unless assignment brief requires it
- Distinguish design criteria (B.P3/B.P4) from execution (C.P5) — never route on Arabic «إنتاج» keyword alone
"""

FILES["ai/ai_detection.md"] = """# AI Detection

- Hybrid score: deterministic metrics + optional LLM detection
- `ai_likelihood` stored in `GradingSummary`
- Advisory only — does not affect BTEC grade band
- Word-only corpus separated from code/vision for detection prompt
"""

# ── pearson/ ──────────────────────────────────────────────────────────────────

FILES["pearson/btec_rules.md"] = """# Pearson BTEC Rules

## Band logic

```
all Pass achieved     → at least P
all Pass + Merit      → at least M  
all Pass + Merit + D  → D
any Pass missing      → U (Referral)
```

## Cumulative principle

Merit/Distinction criteria can be academically achieved but **not awardable** if lower Pass criteria fail.

## Institutional vs analytical

- `criteria_score_pct` — average of criterion scores (analytical)
- `grade_level` — institutional band (governing)
"""

FILES["pearson/pass.md"] = FILES["pearson/merit.md"] = FILES["pearson/distinction.md"] = ""  # placeholder fix below

FILES["pearson/pass.md"] = """# Pass Criteria

Typical Unit 8 Pass criteria:

- **B.P3** — Design documentation (GDD, asset table, audience)
- **B.P4** — Visual designs (screens, flowchart)
- **C.P5** — Working prototype — **requires runtime evidence for games**
- **C.P6** — Testing & technical communication — **requires playtest/video/L5**

All four must be achieved for Pass band.
"""

FILES["pearson/merit.md"] = """# Merit Criteria

- **B.M2** — Design review with peers (reviewer notes required)
- **C.M3** — Game refinement based on testing — **requires runtime evidence**

Blocked if any Pass criterion not achieved/awardable.
"""

FILES["pearson/distinction.md"] = """# Distinction Criteria

- **B.D2** — Advanced design analysis
- **C.D3** — Comprehensive presentation and prototype — **requires runtime evidence**

Requires all Pass + Merit criteria awardable.
"""

FILES["pearson/dependencies.md"] = """# Criterion Dependencies

```
B.P3 ─┐
B.P4 ─┼─▶ Pass block ─▶ enables M band
C.P5 ─┤
C.P6 ─┘

B.M2 ─┐
C.M3 ─┴─▶ Merit block ─▶ enables D band

B.D2 ─┐
C.D3 ─┘──▶ Distinction
```

Runtime-dependent: C.P5, C.P6, C.M3, C.D3
"""

# ── reports/ ──────────────────────────────────────────────────────────────────

FILES["reports/report_generator.md"] = """# Report Generator

- PDF: `app/report_generator.py` → `generate_student_report_pdf`
- Word: `main.py` → `download_report_word`
- Batch summary PDF: `generate_batch_summary_report`

## Grade field consistency

| Output | Official grade field |
|--------|---------------------|
| Word (snapshot) | `grade_display_metrics.final_btec_grade` |
| Batch PDF | `_short_btec_grade()` → `institutional_resolution.btec_grade` |
| Individual PDF | `grade_level` (should align with display metrics) |
| Web UI | `inst.btec_grade or summary.grade_level` |
"""

FILES["reports/word_report.md"] = """# Word Report

Route: `GET /api/download-report-word/{submission_id}`

- Re-runs `finalize_grading_criteria_results` before export
- Reads `criteria_results[].achieved` per criterion
- Official grade: `build_grade_display_metrics(snapshot).final_btec_grade`
- Arabic criterion feedback via `teacher_facing_feedback()`
"""

FILES["reports/pdf_report.md"] = """# PDF Report

- Generated at grading time: `uploads/reports/report_{submission_id}.pdf`
- Individual PDF uses `grade_level` directly
- Ensure snapshot includes post-gate `grade_level` before PDF generation
"""

FILES["reports/feedback.md"] = """# Feedback Rules

- Strip `⚠️ [حوكمة BTEC]` prefixes for teachers
- Never show contradictory dual feedback (governance denial + AI success) — sanitize
- `achieved=False` rows: prefix with institutional reason in Arabic
- Runtime gate reason in Arabic explains accepted evidence types
"""

# ── backend/ ──────────────────────────────────────────────────────────────────

FILES["backend/fastapi.md"] = """# FastAPI

- Entry: `main.py` — app instance, middleware, HTML routes
- API routes: `app/routes/grading.py`, `app/routes/*.py`
- Dev server: `run_dev_server.py` port **5557**
- Middleware: `SecurityAbuseMiddleware`, `RateLimitMiddleware` (`production/hardening.py`)
"""

FILES["backend/services.md"] = """# Services

| Service | Module |
|---------|--------|
| Batch grading | `batch_grader.py`, `batch_grade_worker.py` |
| Grading cache | `strict_grading_policy.py` |
| Plagiarism | `batch_grader.check_plagiarism_for_submission` |
| Playtest | `submission_playtest.py` |
| Explainability | `explainability_migration.py` |
"""

FILES["backend/repository.md"] = """# Repository Pattern

SQLAlchemy models in `app/models.py`:

- `BatchGrading` — batch metadata
- `Submission` — student submission + `grading_snapshot_json`
- `GradingResult` — per-criterion rows (UI results page)
- `GradingSummary` — overall grade, percentage, feedback

Sync: `sync_criteria_results_to_db()` keeps ORM aligned with snapshot.
"""

FILES["backend/database.md"] = """# Database

- SQLite: `ai_grader.db` (gitignored)
- Migrations: auto-create on startup
- Snapshot JSON is authoritative for PRO diagnostics
- ORM may lag — always prefer snapshot on results reload
"""

FILES["backend/api.md"] = """# Key API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/batch-grade/{assignment_id}` | Start batch grading |
| `GET /api/batch-grade-progress/{id}` | Poll progress |
| `GET /api/batch-grade-latest/{id}` | Latest batch meta |
| `GET /api/batch-meta/{batch_id}` | Verify batch exists |
| `GET /batch-results/{batch_id}` | Results HTML |
| `GET /api/download-report-word/{sub_id}` | Word export |
| `POST /api/preflight-evidence/{id}` | Preflight scan |

Rate-limit exempt: batch-results GET, batch-grade-progress GET
"""

# ── frontend/ ─────────────────────────────────────────────────────────────────

FILES["frontend/ui.md"] = """# UI

- Arabic RTL templates in `app/templates/`
- Key pages: `batch_grade.html`, `batch_results.html`, `results.html`
- Toast notifications for grading state
- Progress overlay with real-time polling
"""

FILES["frontend/dashboard.md"] = """# Dashboard

- Admin: `admin.html` — submissions list, `grade_level` from DB
- Graded students: `graded_students.html`
- Batch results PRO table: achieved + awardable columns
"""

FILES["frontend/javascript.md"] = """# JavaScript

- `app/static/js/background_grading.js` — background grading mode
- `batch_grade.html` inline JS — polling, `openBatchResultsSafe`, `finishBatchGradingUI`
- Fix: allow redirect when DB batch `completed` even if `finished` flag delayed
"""

FILES["frontend/bootstrap.md"] = """# Bootstrap / Styling

- Dark theme with green accents
- Custom CSS in templates (not separate bootstrap bundle in all pages)
- File list with per-student status badges (مكتمل / فشل)
"""

# ── security/ ─────────────────────────────────────────────────────────────────

FILES["security/secure_coding.md"] = """# Secure Coding

- Never log API keys or student PII
- `SECRET_KEY` required in production
- `.env` gitignored — use `.env.example` only
- Sanitize filenames on upload
- WhatsApp session tokens never committed
"""

FILES["security/upload_validation.md"] = """# Upload Validation

- Archive extraction with size limits
- RAR/ZIP selective extract (skip Library/Temp/.godot)
- `archive_extraction_utils.py`
- Single-student archive mode for PRO uploads
"""

FILES["security/sandbox.md"] = """# Sandbox

- L4 runtime in isolated observation (not full VM isolation)
- GameMaker/Unity exe launched with timeout
- Screenshots saved to `uploads/debug/runtime_screenshots/` (gitignored)
- Structure-only analysis cannot escape to PASS
"""

FILES["security/authentication.md"] = """# Authentication

- `app/auth/core.py` — session auth
- Role-based: admin, teacher
- `assignment_access.py` — per-assignment permissions
- OAuth Google optional — credentials in `.env` only
"""

# ── testing/ ──────────────────────────────────────────────────────────────────

FILES["testing/pytest.md"] = """# pytest

```bash
python -m pytest tests/test_runtime_evidence_gate.py -q
python -m pytest tests/test_btec_criteria_governance.py -q
python -m pytest tests/test_criteria_result_finalizer.py -q
python -m pytest tests/test_scratch_diagnostics.py -q
```

Use `skip_heavy_enrichment=True` for fast Scratch static tests.
"""

FILES["testing/integration.md"] = """# Integration Tests

- `tests/test_http_e2e.py` — HTTP endpoints
- `tests/test_batch_checkpoint_resume.py` — worker resume
- Full suite slow (~1h) — run targeted subsets in CI
"""

FILES["testing/runtime_testing.md"] = """# Runtime Testing

- `tests/test_runtime_orchestrator.py`
- `tests/test_gamemaker_runtime_verification.py`
- `tests/runtime_stress/` — stress battery (optional, slow)
"""

FILES["testing/governance_testing.md"] = """# Governance Testing

Critical regressions:

1. Scratch `.sb3` must not get false "no project files" demotion
2. Runtime gate blocks P5/P6 without video/L5/runtime PASS
3. Gameplay video satisfies gate
4. `runtime_gate_block` prevents finalizer re-promotion
5. Early governance stub must not demote on empty inventory
"""

# ── prompts/ ──────────────────────────────────────────────────────────────────

FILES["prompts/debugging.md"] = """# Debugging Prompt

When debugging a false U grade:

1. Read `grading_snapshot_json` for submission
2. Check `runtime_evidence_gate` block in snapshot
3. Check `btec_criteria_governance.changes`
4. Verify `artifact_inventory.runtime_artifacts.scratch_detected`
5. Check if `finalize_grading_criteria_results` ran after governance
6. Compare `achieved` vs `awardable` per criterion
"""

FILES["prompts/code_review.md"] = """# Code Review Prompt

Review checklist for grading PRs:

- [ ] Does change run before or after governance?
- [ ] Can it re-promote `runtime_gate_block` rows?
- [ ] Are Arabic diagnostics accurate (detected vs verified)?
- [ ] Tests added for governance/runtime paths?
- [ ] No secrets or student data in diff?
"""

FILES["prompts/architecture.md"] = """# Architecture Prompt

When adding a new grading layer:

1. Document position in pipeline (dependency_graph.md)
2. If it sets `achieved=True`, ensure Runtime Gate still runs after
3. Prefer extending `game_engine_signatures.py` over duplicating extensions
4. Update skill pack CHANGELOG
"""

FILES["prompts/performance.md"] = """# Performance Prompt

- Use `grading_mode=fast` for preflight-only scans
- `skip_runtime_observation=True` in unit tests
- Batch worker: set `finished=True` before slow PDF generation
- Exempt UI polling from global rate limit
"""

FILES["prompts/refactoring.md"] = """# Refactoring Prompt

Safe refactors:

- Consolidate engine signatures into `game_engine_signatures.py`
- Move promotion logic out of finalizer into governance (preferred long-term)
- Unify grade display to always call `build_grade_display_metrics`

Unsafe without tests:

- Changing `determine_grade_level` band thresholds
- Removing `runtime_gate_block` checks
"""


def write_tree(base: Path) -> None:
    if base.exists():
        import shutil
        shutil.rmtree(base)
    base.mkdir(parents=True)
    for rel, content in FILES.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")


def build_zip(base: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(base.rglob("*")):
            if f.is_file():
                arc = f.relative_to(base.parent)
                zf.write(f, arc.as_posix())


def build_perplexity_upload_zip(base: Path, zip_path: Path) -> None:
    """SKILL.md at zip root (Perplexity Spaces upload requirement)."""
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(base.rglob("*")):
            if f.is_file():
                arc = f.relative_to(base)
                zf.write(f, arc.as_posix())


def main() -> None:
    write_tree(ROOT)
    build_zip(ROOT, ZIP_OUT)
    build_perplexity_upload_zip(ROOT, ZIP_PERPLEXITY)
    print(f"Created: {ZIP_OUT}")
    print(f"Perplexity upload: {ZIP_PERPLEXITY}")
    print(f"Files: {len(FILES)}")
    print(f"Size: {ZIP_OUT.stat().st_size / 1024:.1f} KB / {ZIP_PERPLEXITY.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
