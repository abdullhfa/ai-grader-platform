# pytest

```bash
python -m pytest tests/test_runtime_evidence_gate.py -q
python -m pytest tests/test_btec_criteria_governance.py -q
python -m pytest tests/test_criteria_result_finalizer.py -q
python -m pytest tests/test_scratch_diagnostics.py -q
```

Use `skip_heavy_enrichment=True` for fast Scratch static tests.
