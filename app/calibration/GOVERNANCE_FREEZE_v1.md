# GOVERNANCE_FREEZE_v1

**Status:** FROZEN — baseline before sandbox (L4) or agentic runtime observation.

**Date:** 2026-05-22  
**Companion docs:** [`GOVERNANCE_POSITIONING.md`](GOVERNANCE_POSITIONING.md), [`EVIDENCE_GOVERNANCE_ROADMAP.md`](EVIDENCE_GOVERNANCE_ROADMAP.md), [`EVIDENCE_LANGUAGE_CONTRACTS.md`](EVIDENCE_LANGUAGE_CONTRACTS.md)

---

## Purpose

Institutional baseline for **epistemically-governed assessment computation**.  
Any change to authority semantics after this freeze requires explicit governance review.

```text
ingestion semantics ≠ grading authority
runtime observation ≠ criterion authority
video raises plausibility, not authority
contradictions downgrade authority — not automatic failure
```

---

## Frozen modules (v1)

| Module | Role | Max auto authority |
| ------ | ---- | ------------------ |
| `artifact_inventory.py` | Artifact awareness + inventory JSON | L1 acknowledgment |
| `evidence_authority_mapping.py` | Allowed/forbidden claims | L3 ceiling |
| `cross_artifact_consistency.py` | Cross-artifact ambiguity | signal only |
| `gameplay_video_inference.py` | L3 temporal hints | advisory L3 |
| `temporal_consistency_governance.py` | Temporal contradiction signals | downgrade only |
| `evidence_trace_graph.py` | Provenance graph | read-only |
| `authority_replay.py` | Replay viewer data | read-only |

---

## Runtime evidence ladder (frozen)

| Level | Label | Auto-assigned? |
| ----- | ----- | -------------- |
| L0 | no runtime evidence | yes |
| L1 | executable detected | yes |
| L2 | screenshot candidates | yes |
| L3 | gameplay footage / temporal hints | yes |
| L4 | runtime observed (sandbox) | **NO — reserved** |
| L5 | human-verified replay | **NO — reserved** |

---

## Explicit non-goals (frozen until v2 review)

- Auto-run uploaded executables
- `.exe` / `.apk` → criterion Achieved
- Vision «gameplay narration» as authority
- `gameplay verified` / `criterion confirmed` language
- Contradiction → automatic Not Achieved
- Shadow sufficiency → wire to `achieved`

---

## Claim authority flags schema (frozen)

```json
{
  "overclaims": [{ "kind": "overclaim_drift", "criterion": "...", "violations": [] }],
  "temporal_consistency": [{ "kind": "temporal_consistency_signal", "code": "..." }]
}
```

Flags are **governance signals** — they do not mutate grades in v1.

---

## Evidence trace graph (frozen shape)

```text
artifact → hint → corroboration → authority → claim_boundary
              ↓
        contradiction (downgrades)
```

Persisted on: `grading_snapshot.artifact_inventory`, `grading_snapshot.evidence_trace_graph`.

---

## Pre-sandbox checklist

Before implementing L4 controlled sandbox:

- [ ] Human-labelled cohort pilot (20–30) — [`HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md`](HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md)
- [ ] Authority Replay reviewed on real submissions
- [ ] Language contract audit on PDF/Word exports
- [ ] Mitigation memory effectiveness reviewed
- [ ] [`RUNTIME_OBSERVATION_CONTRACT_v1.md`](RUNTIME_OBSERVATION_CONTRACT_v1.md) governance sign-off
- [ ] Explicit GOVERNANCE_FREEZE_v2 RFC if semantics change

---

## Machine-readable snapshot

See [`GOVERNANCE_FREEZE_v1.json`](GOVERNANCE_FREEZE_v1.json).

---

## Drift defense (post-freeze)

Module: `app/governance_drift_monitor.py`

Detects **silent authority inflation** against this freeze:

- forbidden / stronger claim language in outputs
- runtime level above L3 auto-ceiling
- contradictions not surfaced in `claim_authority_flags` or replay
- missing provenance when governance artifacts exist

API: `/api/governance-drift/{submission_id}`, `/api/governance-drift/batch/{batch_id}`

Human pilot metrics: [`HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md`](HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md)

Failure taxonomy: [`GOVERNANCE_FAILURE_TAXONOMY_v1.md`](GOVERNANCE_FAILURE_TAXONOMY_v1.md)

Response protocols: [`GOVERNANCE_RESPONSE_PROTOCOLS_v1.md`](GOVERNANCE_RESPONSE_PROTOCOLS_v1.md)

Mitigation memory: [`GOVERNANCE_MITIGATION_MEMORY_v1.md`](GOVERNANCE_MITIGATION_MEMORY_v1.md)

Runtime chain (post-pilot): [`RUNTIME_EVIDENCE_CHAIN_ROADMAP.md`](RUNTIME_EVIDENCE_CHAIN_ROADMAP.md)

L4 contract (frozen, pre-sandbox): [`RUNTIME_OBSERVATION_CONTRACT_v1.md`](RUNTIME_OBSERVATION_CONTRACT_v1.md)
