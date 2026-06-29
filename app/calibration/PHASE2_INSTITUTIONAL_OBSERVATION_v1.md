# Phase 2 — Institutional Observation v1

**Status:** Active — complete properly before any Phase 3 discussion  
**Mode:** `observe_only` — not a technical expansion phase

## What exists vs what is missing

| Built | Not yet |
|-------|---------|
| architecture | historically grounded behavioural evidence |
| instrumentation | real facilitator hesitation |
| constitutional containment | real leakage patterns |
| replay discipline | ritual reading completion |
| corpus invariants (80/80) | semantic memory from live workshop |

```text
The architecture looks ready ≠ humans are ready
```

---

## Core question (live — unknown until workshop completes)

```text
what does runtime observability do to institutional judgement?
```

Not: *can the system observe runtime?*

---

## Mandatory sequence (do not skip steps)

### 1. Full real workshop

- 20–30 **real** submissions (Godot · Unity · exe + video + screenshots)
- **Real** facilitators
- **Real** runtime evidence · replay · hesitation · leakage
- **Observe only** — no correction · no coaching · no semantic steering

### 2. First real epistemic synthesis

```http
GET /api/governance-pilot/epistemic-evidence/batch/{batch_id}
```

Not readiness score · not L4 · not activation.

Requires ≥20 human observations for `historically grounded` status.

### 3. Complete workshop → cooling (3–7 days)

```http
POST /api/governance-pilot/phase2/cohort/{batch_id}/complete
{ "cooling_days": 5 }
```

No: new rules · mitigations · freeze evolution · leakage controls.

### 4. Ritual reading (slow)

`/governance-pilot/batch/{batch_id}/ritual-reading`

Read for:

| Lens | Why |
|------|-----|
| replay timing | provenance discipline |
| hesitation disappearance | ambiguity collapse |
| contradiction silence | passive legitimacy |
| persuasive screenshots | observational acceleration |
| «واضح أنها شغالة» | implicit authority formation |
| silence itself | closure pressure |

**Not:** who was wrong · leakage count.

### 5. Semantic memory — **after reading only**

```http
POST /api/governance/semantic-memory/record
{ "batch_id": N }
```

**Blocked** until ritual reading marked complete.

### 6. Epoch deliberation

After synthesis + cooling + reading + reflection + semantic memory.

**Not** immediately after metrics.

### 7. Phase 3 gate — Institutional Evidence Calibration (preview)

```http
GET /api/governance-pilot/phase2/cohort/{batch_id}
```

Only after Phase 2 fully complete. Phase 3 is **not** runtime expansion:

```text
Phase 3 — Institutional Evidence Calibration
how much institutional confidence should each evidence type legitimately carry?
```

See: [`EVIDENCE_WEIGHT_CALIBRATION_v1.md`](EVIDENCE_WEIGHT_CALIBRATION_v1.md) · [`CONFIDENCE_LANGUAGE_REGISTRY_v1.md`](CONFIDENCE_LANGUAGE_REGISTRY_v1.md)

Principle: **confidence is not authority** — design only, without automatic scoring.

---

## Activation

```http
POST /api/governance-pilot/phase2/cohort/{batch_id}/activate
```

Opens `/governance-pilot/batch/{batch_id}` — L4 locked until Phase 2 complete.

---

## What NOT to do now

- Phase 3 calibration (before Phase 2 human evidence complete)
- L4 sandbox deployment
- Constitutional evolution
- Telemetry / runtime authority broadening
- Hidden evidence weighting → automatic scoring

Until:

```text
understanding how humans metabolized observability
```

---

## State files

- `app/calibration/human_cohort_workshop/phase2_cohort_state.json`
- `app/calibration/human_cohort_workshop/observations.jsonl`
- `app/calibration/human_cohort_workshop/phase2_ritual_reading_{batch_id}.json`
