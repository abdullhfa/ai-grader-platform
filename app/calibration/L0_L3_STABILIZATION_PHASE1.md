# L0–L3 Stabilization — Phase 1 (Constitutional Foundation)

**Status:** engineering baseline for Phase 1 gate  
**Freeze:** [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md)  
**Roadmap:** [`RUNTIME_EVIDENCE_CHAIN_ROADMAP.md`](RUNTIME_EVIDENCE_CHAIN_ROADMAP.md)

---

## Goal

Prevent **authority inflation** before increasing observability.

```text
runtime evidence entered the chain
without silently becoming authority
```

---

## 1. L0–L3 refinement (complete in code)

Every runtime-related claim must carry:

| Field | Module |
| ----- | ------ |
| `authority_level` | `runtime_claims_registry` |
| `ambiguity_state` | `l2_l3_corroborative_runtime.ambiguity_flags` |
| `corroboration_source` | per-claim provenance |
| `claim_boundary` | `evidence_authority_mapping` + contract |

**Implementation:** `app/runtime_claim_contract.py` → attached to `artifact_inventory.runtime_claims_registry`.

**Replay:** `app/authority_replay.py` — L2/L3 hints + ambiguity steps before claim boundary.

**Drift:** `governance_drift_monitor` — checks `runtime_claim_contract_complete`, `l2_l3_authority_auto_inferred`.

**Language:** [`EVIDENCE_LANGUAGE_CONTRACTS.md`](EVIDENCE_LANGUAGE_CONTRACTS.md) + `GOVERNANCE_FREEZE_v1.json` forbidden claims.

---

## 2. Runtime evidence calibration corpus (50–100 cases)

**Not grading accuracy.** Tests governability invariants:

- L2 screenshots enter chain correctly
- Godot/engine assets excluded from L2
- Video does not create authority leakage
- Contradictions remain visible
- Claims registry contract complete
- Replay shows claim boundary

```bash
python -m app.calibration.runtime_evidence_corpus.generate_corpus --count 80
python -m app.calibration.runtime_evidence_corpus.run_corpus
```

Output: `app/calibration/runtime_evidence_corpus/corpus_last_run.json`

---

## 3. Replay-first workflow (facilitator)

**Gate:** `governance_pilot_observatory.validate_replay_first()`

Every facilitator worksheet requires `section_b.replay_opened = true` before save.

Worksheet draft includes `replay_first_gate` with locked sections until replay consulted.

URL: `/authority-replay/{submission_id}`

---

## Phase 1 exit gate (human + corpus)

| Measure | Target |
| ------- | ------ |
| Corpus invariant pass rate | ≥ 95% on 80-case corpus |
| `runtime_claim_contract_complete` | 100% on graded snapshots with runtime artifacts |
| `replay_presence_rate` | ≥ 0.95 |
| `l3_verification_confusion_rate` | 0 (workshop) |
| Human pilot observations | 20–30 real submissions logged |

**Do not enable L4 sandbox until Phase 1 exit gate is signed.**

---

## Reference case

Ahmed (`batch 1`) — layers visible:

| Layer | State |
| ----- | ----- |
| L1 | exe / Godot / video detected |
| L2 | 2 screenshots in `صور تشغيل اللعبة` (28 Godot assets excluded) |
| L3 | video frames extracted, linkage flag preserved |
| Authority | not auto-inferred |
| Grade | U (correct — Pass criteria incomplete) |
