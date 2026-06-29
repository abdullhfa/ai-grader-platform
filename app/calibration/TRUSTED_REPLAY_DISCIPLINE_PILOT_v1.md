# TRUSTED REPLAY DISCIPLINE PILOT v1

**Pilot ID:** `TRUSTED_REPLAY_DISCIPLINE_PILOT_v1`  
**Status:** DESIGN / ADVISORY — **not** grading pilot · **not** L4 activation  
**Prerequisite:** [`REPLAY_GATE_DISCIPLINE_v1.md`](REPLAY_GATE_DISCIPLINE_v1.md) · [`EXIT_CRITERIA_TRACKING_WORKSHOP_v1.md`](EXIT_CRITERIA_TRACKING_WORKSHOP_v1.md)  
**Parallel track:** exit criteria tracking (metrics) · this pilot (replay precedence behaviour)

Machine-readable: [`TRUSTED_REPLAY_DISCIPLINE_PILOT_v1.json`](TRUSTED_REPLAY_DISCIPLINE_PILOT_v1.json)

---

## Institutional invariant

```text
Containment evidence is not activation evidence.
```

---

## Purpose

Test whether **replay timing** changes **authority formation behaviour** — not whether replay **exists**.

Batch 4 proved:

```text
replay opened ≠ replay trusted
replay present ≠ replay before judgment
```

### Core pilot question

```text
Does replay timing alter authority formation behaviour?
```

**Not:**

```text
Was replay opened?
```

---

## Pilot posture

| Is | Is not |
| -- | ------ |
| design/advisory observation protocol | grading pilot |
| timing + precedence analysis | replay UI feature test |
| authority formation behaviour study | trusted replay certification |
| worksheet-driven human observation | automatic gate wire |

---

## What «trusted replay discipline» means (institutional)

Replay has **precedence over intuition** when:

1. `replay_consulted_at` is set **before** verification lexicon appears
2. `authority_language_first_at` = `after_replay` or `never` — not `before_replay`
3. Gate 3 advisory pass correlates with **delayed** not **absent** authority language
4. Reviewer can articulate provenance chain after consult — not aesthetic closure

**Trusted** = temporal discipline + provenance consult — not API availability.

---

## Pilot design (advisory only)

### Comparison dimensions

| Dimension | Procedural replay (Batch 4 baseline) | Trusted discipline target |
| --------- | ------------------------------------ | ------------------------- |
| replay opened | ~21/21 | same |
| replay_consulted_at set | 1/21 | increase |
| replay_before_judgment=yes | 1/21 | increase |
| authority before replay | common (#3 · #13) | rare |
| Gate 3 pass (advisory) | minority | majority under runtime claims |

### Observation worksheet (per submission)

| Field | Purpose |
| ----- | ------- |
| `replay_opened_at` | timestamp |
| `first_authority_language_at` | before / during / after / never |
| `replay_consulted_at` | timestamp or null |
| `timing_delta_ar` | did consult precede verification lexicon? |
| `authority_formation_altered` | yes / no / partial — facilitator judgment |
| `intuition_would_have_closed` | yes / no — counterfactual |

### Pilot success test

```text
In advisory observation sample (≥5 submissions):
replay_consulted_at precedes verification language in majority
AND authority_language_first_at ≠ before_replay in majority
→ evidence that timing CAN alter behaviour (not yet institutional trust)
```

**Failure mode:** replay opened habitually · consult null · authority forms anyway → discipline not trusted.

---

## Session anchors (from Path A curriculum)

| Session | Replay timing lesson |
| ------- | -------------------- |
| #3 | authority language **before** replay — failure |
| #2 | replay consulted — restraint easier |
| #4 | partial replay · anchors prevent closure despite gap |
| #13 | strong evidence · Gate 3 fail · partial legitimacy |

---

## Forbidden pilot outcomes

- «Replay works» → activate L4
- «Consult rate improved» → freeze v2
- Wire gates to grading automatically
- Skip exit criteria tracking workshop
- Certify replay trusted from pilot alone

---

## Relationship to exit criteria

| Exit criterion | Pilot contributes |
| -------------- | ----------------- |
| trusted replay discipline | **primary** — precedence evidence |
| automated quarantine enforcement | no — separate track |
| QB recurrence reduction | indirect — via M1 metric |
| independent human audit | pilot worksheets = audit input |

Pilot evidence **feeds** exit criteria tracking — **does not** satisfy exit criteria alone.

---

## Explicit non-goals

- Grading pipeline integration
- L4 sandbox build
- Replay engine automation
- Replacing Authority Replay UI
- Institutional certification of «replay trusted=yes»

---

## Lineage

| Ref | Role |
| --- | ---- |
| `led_8f0ec9362fa3` | replay-before-judgment fragility |
| `REPLAY_GATE_DISCIPLINE_v1` | Gate 3 definition |
| `EXIT_CRITERIA_TRACKING_WORKSHOP_v1` | M1 metric |
| Batch 4 · sessions #3 #13 | failure anchors |

**Facilitator:** Eng.Abdulah · **Mode:** design/advisory · **Activated:** 2026-05-25
