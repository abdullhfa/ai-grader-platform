# Performance Prompt

- Use `grading_mode=fast` for preflight-only scans
- `skip_runtime_observation=True` in unit tests
- Batch worker: set `finished=True` before slow PDF generation
- Exempt UI polling from global rate limit
