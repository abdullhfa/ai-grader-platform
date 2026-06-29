# Evidence Registry

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
