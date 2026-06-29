# System Architecture

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
