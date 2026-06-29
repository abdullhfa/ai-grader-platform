# Folder Structure

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
