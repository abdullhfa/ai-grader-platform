# Governance backlog

## Production Performance — High Priority: bounded source-file scan

`app.academic_explainability._count_cs_on_disk` is invoked on the production
grading path: `batch_grader` → `build_artifact_inventory` →
`attach_academic_explainability` → `_count_cs_on_disk`. A large Godot/PCK
submission can make its unconstrained `Path.rglob()` scan exceed the execution
budget. Replace it in a separate change with a bounded traversal and a
documented `PARTIAL_SCAN` outcome on soft timeout; do not change student grades
as part of that performance work.

## Test Environment: isolate external AI provider health checks

`tests/test_http_e2e.py::TestHttpE2E::test_health_deep` performs a live provider
health check and retries when Ollama/OpenAI is unavailable. Make the test
self-contained by injecting or mocking provider health in a separate change;
do not treat external network availability as a unit-test requirement.
