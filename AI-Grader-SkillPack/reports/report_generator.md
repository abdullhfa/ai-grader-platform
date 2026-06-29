# Report Generator

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
