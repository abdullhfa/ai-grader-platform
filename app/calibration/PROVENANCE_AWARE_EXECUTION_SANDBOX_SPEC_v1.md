# Provenance-Aware Execution Sandbox Spec v1

**Step:** 3 of `RUNTIME_OBSERVABILITY_PREPARATION_v1`  
**Status:** design-only — **not** activation · **not** authority  
**Extends:** [`PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.md`](PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.md)

Machine-readable: [`PROVENANCE_AWARE_EXECUTION_SANDBOX_SPEC_v1.json`](PROVENANCE_AWARE_EXECUTION_SANDBOX_SPEC_v1.json)

---

## Primary invariant

```text
Execution is observable before it is trustworthy.
```

**Not:** *If the exe ran, we have runtime truth.*

---

## First sandbox invariant

```text
Visible execution is not equivalent to validated execution.
```

This is the runtime counterpart of constitutional epistemics in the linguistic domain:

```text
runtime visibility  ≠  runtime legitimacy
```

---

## Sandbox layer matrix

| Layer | Allowed |
|-------|---------|
| process launch | observation |
| window detection | observation |
| telemetry stream | observation |
| frame capture | observation |
| input playback | observation |
| execution continuity | observation |
| provenance chain link | observation |
| gameplay legitimacy | **forbidden** |
| rubric achievement | **forbidden** |
| success inference | **forbidden** |

---

## Execution phenomenology (new layer)

The system describes **what appeared during execution** — not **what it means**.

| Phenomenology | Forbidden escalation |
|---------------|---------------------|
| process launched | game works |
| frames rendered | gameplay verified |
| input responded | mechanics validated |
| executable persisted | rubric achieved |
| window detected | game confirmed |
| telemetry stream active | runtime truth established |
| replay captured | provenance validated |

Module: `app/execution_phenomenology.py`  
Schema: [`EXECUTION_PHENOMENOLOGY_SCHEMA_v1.json`](EXECUTION_PHENOMENOLOGY_SCHEMA_v1.json)

---

## Supreme risk: simulation confidence drift

When humans see:

- a window open
- movement
- frames
- telemetry
- replay

They automatically feel: *the game is confirmed.*

Even when:

- corroboration is missing
- identity is not bound
- gameplay is not understood
- replay is not provenanced

**Mitigation:** phenomenology layer · forbidden escalation table · **empty ledger by default**

```text
runtime_observation_ledger.jsonl intentionally empty
```

Protective ambiguity applies to runtime — telemetry presence ≠ the system understands the game.

---

## Provenance requirements (design)

| Requirement | Status |
|-------------|--------|
| continuity tracking | design target |
| artifact identity binding | required before trust claims |
| replay determinism | design target |
| corroboration gate | human-governed |

```text
observation chain  ≠  validation chain
```

---

## Constitutional transfer

If this phase preserves:

```text
runtime visibility ≠ runtime legitimacy
```

Then constitutional epistemics successfully transfers from **linguistic domain** → **runtime execution domain**.

---

## Blocked

- sandbox activation  
- gameplay legitimacy inference  
- rubric wire  
- success inference language  

Ledger: [`runtime_observation_ledger.jsonl`](human_cohort_workshop/runtime_observation_ledger.jsonl) — empty intentionally.
