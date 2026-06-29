# AI-Grader Skill Pack (Pearson BTEC)

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
