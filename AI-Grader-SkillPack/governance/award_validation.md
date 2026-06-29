# Award Validation

## Two orthogonal fields

| Field | Drives |
|-------|--------|
| `achieved` | Academic verification — did student meet criterion? |
| `awardable` | Institutional grant — can BTEC band include this criterion? |

Example: B.M2 `achieved=True` but `awardable=False` when C.P6 Pass is missing (cumulative block).

## Runtime-gated criteria

`RUNTIME_GATED_SHORT = {P5, P6, M3, D3}`

Cannot be `achieved=True` for game submissions without:
- Runtime PASS, OR gameplay video, OR L5 playtest

## Validation tests

- `tests/test_btec_criteria_governance.py`
- `tests/test_runtime_evidence_gate.py`
- `tests/test_criteria_result_finalizer.py`
