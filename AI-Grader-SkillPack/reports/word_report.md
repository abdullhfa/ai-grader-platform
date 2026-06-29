# Word Report

Route: `GET /api/download-report-word/{submission_id}`

- Re-runs `finalize_grading_criteria_results` before export
- Reads `criteria_results[].achieved` per criterion
- Official grade: `build_grade_display_metrics(snapshot).final_btec_grade`
- Arabic criterion feedback via `teacher_facing_feedback()`
