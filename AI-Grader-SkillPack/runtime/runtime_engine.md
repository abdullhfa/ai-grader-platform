# Runtime Engine

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
