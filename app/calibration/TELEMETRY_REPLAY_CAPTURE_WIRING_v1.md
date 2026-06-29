# Step 4 — Telemetry + Replay Capture Wiring v1

**Phase:** `RUNTIME_OBSERVABILITY_PREPARATION_v1`  
**Status:** design-only — **not** activation  
**Extends:** [`PROVENANCE_AWARE_EXECUTION_SANDBOX_SPEC_v1.md`](PROVENANCE_AWARE_EXECUTION_SANDBOX_SPEC_v1.md)

Machine-readable: [`TELEMETRY_REPLAY_CAPTURE_WIRING_v1.json`](TELEMETRY_REPLAY_CAPTURE_WIRING_v1.json)

---

## Primary invariant

```text
Telemetry density does not imply gameplay understanding.
```

**Supreme risk:** epistemic saturation — more signals → false sense the system *understands* what is happening.

---

## Replay invariant

```text
Replay is evidence of reproducibility,
not evidence of validity.
```

Ordered replay + coherent telemetry + continuous execution  
→ danger: *game confirmed*  
→ **legitimacy illusion**

---

## Core split

```text
execution visibility  ≠  execution comprehension
```

Prevent:

```text
high-resolution legitimacy theater
```

Technical signal density without epistemic verification.

---

## Two-layer telemetry architecture

| Layer | Function |
|-------|----------|
| **raw telemetry** | capture only |
| **epistemic interpretation** | **blocked by default** |

### Raw telemetry (phenomenological traces)

- FPS samples  
- frame events  
- process lifecycle  
- input timestamps  
- crash signals  
- render continuity  

Stored as **phenomenological traces** — not meaningful gameplay claims.

### Epistemic interpretation

- Default: **blocked**  
- Unlock: human-governed explicit gate only  
- Never: auto-inference from signal density  

---

## Replay phenomenology

| Replay phenomenology | Forbidden escalation |
|---------------------|------------------------|
| replay captured | gameplay verified |
| replay deterministic | submission authentic |
| replay reproducible | rubric satisfied |
| replay continuous | mechanics validated |

Schema: [`REPLAY_PHENOMENOLOGY_SCHEMA_v1.json`](REPLAY_PHENOMENOLOGY_SCHEMA_v1.json)  
Module: `app/telemetry_replay_capture.py`

---

## Wiring outputs (allowed)

- raw telemetry traces  
- telemetry graph  
- replay phenomenology  
- provenance chain segment  
- epistemic interpretation blocked stub  

## Forbidden outputs

- gameplay understood  
- gameplay verified  
- submission authentic  
- rubric satisfied  
- mechanics validated  
- high-resolution legitimacy summary  

---

## Ledger discipline

[`runtime_observation_ledger.jsonl`](human_cohort_workshop/runtime_observation_ledger.jsonl) — **intentionally empty**.

Protective ambiguity applies to telemetry density as well as execution visibility.

---

## Constitutional transfer

If this step preserves:

```text
execution visibility ≠ execution comprehension
```

Then constitutional epistemics transfers from **text and language** → **telemetry and runtime signals**.
