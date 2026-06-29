# Repository Pattern

SQLAlchemy models in `app/models.py`:

- `BatchGrading` — batch metadata
- `Submission` — student submission + `grading_snapshot_json`
- `GradingResult` — per-criterion rows (UI results page)
- `GradingSummary` — overall grade, percentage, feedback

Sync: `sync_criteria_results_to_db()` keeps ORM aligned with snapshot.
