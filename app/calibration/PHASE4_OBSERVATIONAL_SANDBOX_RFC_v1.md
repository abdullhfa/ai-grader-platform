# PHASE 4 — Observational Sandbox RFC v1

**RFC ID:** `PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1`  
**Status:** DESIGN-ONLY — **not** authority deployment · **not** activation · **not** grading wire  
**Eligibility basis:** [`EPOCH_REREVIEW_PACKET_PATH_A_v1.md`](EPOCH_REREVIEW_PACKET_PATH_A_v1.md) — `mitigation_containment_progress_accepted`  
**Prerequisites:** Path A design layer (REPLAY_GATE · TRIAD_LANGUAGE · QUARANTINE_CONTRACT)

Machine-readable: [`PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.json`](PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.json)

---

## Opening declaration (non-negotiable)

```text
Phase 4 design eligibility derives from containment progress,
not from authority readiness.
```

Arabic:

```text
أهلية تصميم Phase 4 تستمد من تقدّم الاحتواء —
لا من جاهزية السلطة.
```

This RFC **must not** be read as implicit escalation license.  
Mitigation success ≠ authority deployment permission.

---

## Core design question

```text
Can the system observe authority formation without participating in it?
```

If **yes** → L4 **observational sandbox** is architecturally justified **as design**.  
If the system begins to grant legitimacy · suggest Achieved · bypass quarantine → it is **not** observational sandbox — it is **premature governance escalation**.

---

## Institutional axiom

```text
L4 is permitted to witness epistemic formation,
not to finalize it.
```

Arabic:

```text
L4 مُخوّل بمشاهدة تشكّل المعرفة —
لا بإنهائها.
```

Path A goal: **slow legitimacy** — not **automate** it.

---

## Relationship to existing contracts

| Artifact | Relationship |
| -------- | ------------ |
| `RUNTIME_OBSERVATION_CONTRACT_v1` | L4 language ceiling when built — this RFC defines **posture before build** |
| `EPISTEMIC_QUARANTINE_CONTRACT_v1` | L4 outputs inherit quarantine — never lift it |
| `AUTHORITY_TRIAD_LANGUAGE_v1` | L4 may tag epistemic states — may not use forbidden shortcuts |
| `REPLAY_GATE_DISCIPLINE_v1` | L4 observes gate conditions — does not pass gates on behalf of grading |
| `GOVERNANCE_FREEZE_v1` | Active — L4 operational activation **blocked** |

**Companion runtime contract:** [`RUNTIME_OBSERVATION_CONTRACT_v1.md`](RUNTIME_OBSERVATION_CONTRACT_v1.md) (frozen semantics — activation gated separately)

---

## 1. Scope boundary

### Allowed (observational sandbox may)

| Capability | Purpose |
| ---------- | ------- |
| **observe** | structural + runtime signal collection in isolated environment |
| **classify epistemic states** | tag claims: observed · represented · inferred · … per triad vocabulary |
| **detect vocabulary drift** | flag forbidden authority shortcuts (advisory) |
| **detect quarantine breaches** | QB1–QB4 taxonomy signals (advisory) |
| **produce advisory traces** | append to epistemic audit residue — not grading records |
| **replay analysis** | provenance inspection · timing · continuity checks |

### Forbidden (observational sandbox must never)

| Prohibition | Why |
| ----------- | --- |
| **grading authority** | L4 ≠ criterion decision |
| **automatic Achieved assignment** | runtime observed ≠ achieved |
| **quarantine lifting** | constitutional boundary — human + full protocol only |
| **runtime confirmation** | «game verified» · «criterion confirmed» reserved |
| **governance override** | no bypass of freeze · gates · HOLD |
| **replay bypass** | observation does not substitute provenance replay |

```text
If it finalizes legitimacy → out of scope.
If it witnesses formation → in scope.
```

---

## 2. Sandbox epistemic posture

The sandbox **always** defines itself as:

```text
non-authoritative observational layer
```

**Not:**
- assistant grader
- verification engine
- auto-corrector
- semantic closer

### Output identity tag (required on every artifact)

```json
{
  "layer": "L4_observational_advisory",
  "authority_participation": false,
  "grading_wire": false,
  "quarantine_inherited": true
}
```

### Language posture

All L4 RFC outputs use **quarantine-safe** lexicon from `AUTHORITY_TRIAD_LANGUAGE_v1` until explicit post-exit human protocol — even in design prototypes.

---

## 3. Quarantine compatibility

**Invariant:**

```text
L4 may observe authority conditions.
L4 may not grant authority conditions.
```

Every L4 output must:

| Rule | Meaning |
| ---- | ------- |
| **inherit** quarantine state | if submission in `quarantine_maintained` → L4 output tagged quarantined |
| **not lift** quarantine | no `LIFT_*` steps executable by sandbox |
| **not linguistically bypass** | no verification lexicon to «compensate» for missing replay |

### State inheritance chain

```text
submission quarantine state
  → L4 observation session state (inherits)
  → advisory trace output (inherits tag)
  → human reviewer (may deliberate — L5)
```

L4 **never** writes `authority_granted` or `quarantine_lifted`.

---

## 4. Failure containment assumptions

This RFC **assumes mitigation did not «solve» the problem**.

| Assumption | Design response |
| ---------- | --------------- |
| **semantic leakage will recur** | vocabulary drift detection mandatory in observational outputs |
| **vocabulary drift will appear** | triad language checks · QB taxonomy |
| **replay shortcuts will occur** | timing analysis · Gate 3 observability — not trust by default |
| **executable temptation will persist** | #13-class patterns monitored · runtime_authority_gap tagging |
| **partial legitimacy will form** | audit residue · breach severity — not silent acceptance |

```text
Mitigation reduced risk — it did not eliminate epistemic pressure.
```

Observational sandbox exists to **make recurrence visible early** — not to claim containment is complete.

---

## 5. Exit criteria (activation gate)

**Most critical section.** None of the following authorizes activation by itself — all are **mandatory before** wire-integration · authority experimentation · operational sandbox.

| Requirement | Needed | Current status (Batch 4 / Path A) |
| ----------- | ------ | --------------------------------- |
| **trusted replay discipline** | mandatory | **incomplete** — replay_trusted=no |
| **automated quarantine enforcement** | mandatory | **advisory only** — stub eval |
| **breach recurrence reduction evidence** | mandatory | **not demonstrated** — QB2/QB3 documented |
| **no unresolved QB3/QB4 patterns** | mandatory | **unresolved** — #13 partial gap |
| **independent human audit** | mandatory | **pending** — workshop evidence only |

### Additional institutional gates (from L4 decision point)

- [ ] Signed epoch verdict ≠ `mitigation_containment_progress_accepted` alone for activation
- [ ] `GOVERNANCE_FREEZE_v2` RFC — if L4 semantics change
- [ ] `RUNTIME_OBSERVATION_CONTRACT_v1` sign-off for operational build
- [ ] No forbidden L4 language in pilot exports
- [ ] Human review rate tracked for L4-touched submissions

### What exit criteria unlock (when all met + epoch sign-off)

| Unlocks | Still forbidden |
| ------- | --------------- |
| minimal L4 sandbox **pilot** (observational) | auto Achieved |
| runtime telemetry → trace graph | grading wire |
| replay UI for human reviewers | quarantine auto-lift |
| limited institutional deployment **experiment** | L5 replacement |

**Until exit criteria met:** this RFC remains **design specification only**.

**Evidence tracks (non-operational):** [`EXIT_CRITERIA_TRACKING_WORKSHOP_v1.md`](EXIT_CRITERIA_TRACKING_WORKSHOP_v1.md) · [`TRUSTED_REPLAY_DISCIPLINE_PILOT_v1.md`](TRUSTED_REPLAY_DISCIPLINE_PILOT_v1.md)

---

## Architectural shape (design target)

```text
┌─────────────────────────────────────────┐
│  Grading / criterion authority (L5)     │  ← human only
├─────────────────────────────────────────┤
│  Epistemic quarantine contract          │  ← constitutional boundary
├─────────────────────────────────────────┤
│  L4 observational sandbox (this RFC)  │  ← witness · classify · trace
│    · observe · detect · advise          │
│    · NO grant · NO lift · NO achieve    │
├─────────────────────────────────────────┤
│  Replay gate + triad language           │  ← Path A mitigation
├─────────────────────────────────────────┤
│  Artifact inventory L0–L3               │  ← existing pipeline
└─────────────────────────────────────────┘
```

Data flow:

```text
artifacts → L4 observe → epistemic state tags + advisory traces
                        → audit residue (jsonl)
                        → human reviewer (L5 deliberation)
                        ✗ grading engine (forbidden at L4)
```

---

## Explicit non-goals

- Autonomous rubric scoring
- Unsupervised gameplay agents
- Criterion auto-achievement from runtime signals
- «Strong evidence» quarantine bypass
- Implicit GOVERNANCE_FREEZE_v2 activation via RFC acceptance
- Conflating design RFC acceptance with sandbox deployment

---

## Lineage

| Ref | Role |
| --- | ---- |
| `EPOCH_REREVIEW_PACKET_PATH_A_v1` | design eligibility — containment not readiness |
| `REPLAY_GATE_DISCIPLINE_v1` | gate observability |
| `AUTHORITY_TRIAD_LANGUAGE_v1` | language drift detection spec |
| `EPISTEMIC_QUARANTINE_CONTRACT_v1` | state inheritance rules |
| `RUNTIME_OBSERVATION_CONTRACT_v1` | frozen L4 language when operational |
| Workshop sessions #3 · #2 · #4 · #13 | epistemic progression evidence |
| `REFERENCE_GOVERNANCE_COHORT_BATCH4` | historical baseline |

---

## RFC acceptance (design-only)

Acceptance of this RFC means:

```text
Phase 4 observational sandbox architecture is institutionally specified.
Phase 4 operational activation is NOT authorized.
```

**Facilitator:** Eng.Abdulah · **Role:** governance_facilitator  
**Accepted:** 2026-05-25 · **Activation:** false
