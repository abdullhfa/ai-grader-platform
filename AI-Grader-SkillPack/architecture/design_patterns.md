# Design Patterns

## Pipeline + Terminal Seal

Grading uses sequential enrichment layers. The **terminal seal** (`finalize_grading_criteria_results` → Runtime Gate) runs last and cannot be bypassed by earlier promotions.

## Single Source of Truth

- Engine signatures: `game_engine_signatures.py`
- Grade band: `determine_grade_level()` on `achieved`
- Award band (PRO): `institutional_grade_from_awardable()` on `awardable`

## Advisory vs Authority

| Layer | Authority level |
|-------|-----------------|
| Preflight scan | Advisory hint only |
| Vision L3 | Advisory visual inference |
| L4 sandbox | Partial runtime observation |
| L5 human playtest | Governed human review |
| Governance + Gate | **Institutional decision** |

## Hold flags

- `pro_gameplay_governance_hold` — blocks finalizer re-promotion (PRO)
- `runtime_gate_block` — blocks all re-promotion for gated criteria

## Idempotent governance

`apply_runtime_evidence_gate` is safe to call on every snapshot reload (results page, Word export).
