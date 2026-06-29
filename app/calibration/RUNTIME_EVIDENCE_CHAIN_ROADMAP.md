# Runtime Evidence Chain Roadmap

From **governed document assessment** → **institutionally governed runtime evidence assessment**.

**Not:** `AI grading games`  
**Yes:** `runtime evidence became institutionally governable`

Current baseline: [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md) (L0–L3 frozen)

---

## Full sequence (correct order)

```text
1. Pilot governance observatory          ← NOW
2. L4 governed sandbox                   ← after pilot gate
3. Runtime telemetry graph
4. Runtime-to-criterion mapping (advisory)
5. Human-governed runtime review
6. Operational governance validation
7. Limited institutional deployment
```

**Do not skip step 1.** Sandbox before pilot amplifies L3 confusion and modality dominance.

---

## Phase 0 — Complete (L0–L3)

| Layer | Module(s) | Authority ceiling |
| ----- | --------- | ----------------- |
| Artifact awareness | `artifact_inventory.py` | L1 |
| Evidence coverage | coverage matrix, reports | explainability |
| Screenshot / video hints | `gameplay_video_inference.py` | L3 advisory |
| Authority mapping | `evidence_authority_mapping.py` | claim bounds |
| Cross-artifact consistency | `cross_artifact_consistency.py` | ambiguity signal |
| Temporal consistency | `temporal_consistency_governance.py` | downgrade |
| Trace graph | `evidence_trace_graph.py` | provenance |
| Closed-loop regulation | drift, taxonomy, responses, mitigation | self-correction |

---

## Phase 1 — Human Pilot (required next)

**Purpose:** Test whether humans preserve authority boundaries — not whether AI infers gameplay.

Workflow: [`COHORT_OBSERVATORY_WORKFLOW_v1.md`](COHORT_OBSERVATORY_WORKFLOW_v1.md)  
Worksheet: [`GOVERNANCE_PILOT_WORKSHEET_v1.md`](GOVERNANCE_PILOT_WORKSHEET_v1.md)  
UI: `/governance-pilot/batch/{batch_id}`

| Measure | Source |
| ------- | ------ |
| L3 verification confusion | workshop + `l3_verification_confusion_rate` |
| Modality dominance | GFM_MODALITY_DOMINANCE counts |
| Replay interpretation | `replay_consultation_rate` (manual) |
| Downgrade acceptance | workshop rubric |
| Trust retention | survey / workshop |
| Mitigation effectiveness | `GET /api/governance-mitigation/summary` |

Doc: [`HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md`](HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md)

**Exit gate:** Top GFMs documented; trust retention acceptable; no unresolved S5 drift silence.

---

## Phase 2 — L4 Governed Runtime Observation Sandbox

**Purpose:** Observation — not verification.

Contract: [`RUNTIME_OBSERVATION_CONTRACT_v1.md`](RUNTIME_OBSERVATION_CONTRACT_v1.md)  
Freeze v2 (draft): [`GOVERNANCE_FREEZE_v2.md`](GOVERNANCE_FREEZE_v2.md)

**Gate:** L4 sandbox runs only after signed `epoch_transition_justified_institutionally` verdict.  
Decision package: `/governance/l4-decision` · API: `/api/governance/l4-decision/package`

| Does | Does not |
| ---- | -------- |
| Isolated launch | Auto Achieved |
| Screenshot / telemetry capture | «Game verified» |
| Crash / timeout / limits | Autonomous rubric scoring |
| Observation replay | Hidden grade manipulation |

Output language: `runtime observations collected under controlled conditions`

**Module:** `app/runtime_observation_sandbox.py` (implemented — **gated** until FREEZE v2)  
**Telemetry:** `app/runtime_telemetry_graph.py`

---

## Phase 3 — Structured Runtime Telemetry

Replace «AI watched gameplay» with **runtime signal graph**:

| Signal | Example |
| ------ | ------- |
| scene_loaded | yes |
| player_moved | detected |
| score_changed | yes |
| collision_events | observed |
| level_transition | partial |
| crash | none |

Feeds: evidence trace graph → authority negotiation → **not** direct grading.

**Module:** `app/runtime_telemetry_graph.py`

Event types: `process_started`, `scene_loaded`, `input_detected`, `score_changed`, `collision_detected`, `level_transition`, `runtime_duration`, `crash_state`

---

## Phase 4 — Runtime-to-Criterion Mapping (advisory)

| Criterion area | Runtime support signal |
| -------------- | ---------------------- |
| scoring | score delta |
| movement | positional change |
| health/lives | HUD variation |
| progression | scene transitions |
| UI | menu navigation |

```text
mapped evidence ≠ automatic achievement
```

**Module (future):** `app/runtime_criterion_mapping.py`

---

## Phase 5 — Human-Governed Runtime Review

Human remains **final authority** (L5).

UI presents: replay + telemetry + screenshots + contradictions + authority ladder + downgrade flags.

**Module (future):** runtime review panel in Authority Replay viewer

---

## Phase 6 — Operational governance validation

Validate **runtime evidence governability** before wide deployment:

- forbidden L4 language audit
- export policy independence from score
- human review rate for L4 submissions
- GFM recurrence after sandbox enabled

---

## Architecture target

```text
governed runtime evidence chain:

  artifact → hint → corroboration → [L4 runtime signals] → authority → human → claim
```

Grading engine consumes **only** human-governed criterion decisions at L5; all lower layers are advisory.

---

## Explicit non-goals (all phases)

- `runtime observed → criterion achieved`
- AI gameplay narration as authority
- Score-centric export policy
- Sandbox before pilot
- Shadow runtime → auto `achieved` wire
