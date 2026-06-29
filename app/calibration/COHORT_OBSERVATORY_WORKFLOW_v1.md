# Cohort Observatory Workflow v1

> **Phase 2 active:** See `PHASE2_INSTITUTIONAL_OBSERVATION_v1.md` — observe only, Section E before D, cooling period after workshop.

```text
human governance behaviour > any new technical expansion
```

**Do not start L4 sandbox** until this workflow completes.

---

## What you already have

| Capability | Endpoint / module |
| ---------- | ----------------- |
| Authority Replay | `/authority-replay/{id}` |
| Drift monitor | `/api/governance-drift/{id}` |
| Cohort drift | `/api/governance-drift/batch/{id}` |
| Failure taxonomy | `governance_failure_taxonomy.py` |
| Mitigation memory | `/api/governance-mitigation/summary` |
| Export gates | Word export 403 on S5 |
| Evidence ladders | artifact inventory + trace graph |

**Missing until now:** structured human governance observation.

---

## Workflow (20–30 submissions)

### Step 1 — Select cohort

- Mix: exe/apk + video + docx-only + contradictions
- Re-grade if `grading_snapshot` lacks `artifact_inventory`
- Record `batch_id`

### Step 2 — Open observatory

`/governance-pilot/batch/{batch_id}`

For each submission:

1. Read **Section A** (auto-prefill)
2. Open **Authority Replay** in parallel
3. Facilitator leads disagreement discussion
4. Reviewer completes **Sections B–D**
5. Submit observation → `observations.jsonl`

Optional: log acute incidents via `POST /api/governance-workshop/incident`

### Step 3 — Workshop session rules

**Observe:**

- Does reviewer treat L3 as verification?
- Is replay actually opened?
- Is downgrade respected?
- Does human authority creep start?

**Do not:**

- Debate model accuracy as primary metric
- «Fix» disagreements by prompt tuning mid-session
- Treat executable presence as achievement

### Step 4 — Batch governance synthesis (immediately after)

`GET /api/governance-pilot/synthesis/batch/{batch_id}`

Produces: **`institutional_governance_stability_report`**

Review outputs:

| Output | Action |
| ------ | ------ |
| Top GFMs | Workshop debrief + taxonomy update if needed |
| L3 confusion map | Training note if > 0 |
| Replay usage | UX fix if consultation low |
| Trust retention | Process fix if < 3 avg |
| Mitigation effectiveness | Record outcomes |
| Export gates | Confirm S5 blocks worked |
| `ready_for_l4_rfc` | Gate decision |

### Step 5 — Pilot gate decision

**If pass:** open RFC for L4 sandbox per [`RUNTIME_OBSERVATION_CONTRACT_v1.md`](RUNTIME_OBSERVATION_CONTRACT_v1.md)

**If fail:** repeat workshop slice — **not** sandbox, **not** prompt tuning

---

## Correct sequence

```text
Pilot governance observatory
→ batch governance synthesis
→ institutional stability review
→ (optional) L4 RFC
```

**Wrong sequence:**

```text
workshop → prompt tuning → sandbox   ❌
```

---

## Files

| File | Content |
| ---- | ------- |
| `observations.jsonl` | Full worksheets (B–D manual) |
| `incidents.jsonl` | Acute GFM incidents |
| `mitigations.jsonl` | Mitigation outcomes |

Directory: `app/calibration/human_cohort_workshop/`

---

## Success definition

Not:

```text
AI accuracy report
```

Yes:

```text
institutional governance stability report
```

Human reviewers preserve authority boundaries under disagreement — or you know exactly where they fail.
