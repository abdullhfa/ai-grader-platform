# Runtime Observation Contract v1

**Status:** FROZEN — prerequisite for any L4 sandbox work.  
**Design RFC (no activation):** [`PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.md`](PHASE4_OBSERVATIONAL_SANDBOX_RFC_v1.md)  
**Companion:** [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md), [`EVIDENCE_LANGUAGE_CONTRACTS.md`](EVIDENCE_LANGUAGE_CONTRACTS.md)

Implementation stub: `app/runtime_observation_contract.py`

---

## Core axiom

```text
runtime observed ≠ criterion achieved
```

Correct chain:

```text
runtime observed
  → runtime evidence generated
  → authority negotiated
  → human review
  → criterion decision
```

**Forbidden shortcut:**

```text
runtime observed → therefore criterion achieved   ❌
```

---

## Semantic contracts (frozen)

| Term | Institutional meaning | Authority level |
| ---- | --------------------- | --------------- |
| `runtime_observed` | Executable launched in controlled sandbox | L4 partial observation |
| `gameplay_hints` | Interaction traces inferred from telemetry | L4 advisory |
| `runtime_stable` | No crash during bounded observation window | L4 signal |
| `telemetry_corroborated` | Multiple runtime signals align | L4 corroborated advisory |
| `operational_evidence` | Structured runtime signals in trace graph | **Advisory only** |
| `verified_achievement` | Criterion met with institutional authority | **L5 human-governed only** |

---

## Allowed language (L4 sandbox output)

| Use | Example |
| --- | ------- |
| Observation | «Executable launched in controlled sandbox. Limited runtime observations collected.» |
| Signals | «Player positional change detected; score delta observed.» |
| Stability | «No crash during 120s observation window.» |
| Corroboration | «Telemetry partially corroborates documentation claims.» |
| Uncertainty | «Runtime evidence advisory — human review required for criterion authority.» |

---

## Forbidden language (L4 — never auto-generated)

| Forbidden | Why |
| --------- | --- |
| game completed | Implies full rubric satisfaction |
| criteria verified | Confuses observation with achievement |
| gameplay confirmed | Narrative authority inflation |
| C.P5 Achieved because game ran | Runtime ≠ criterion |
| verified achievement (without L5) | Reserved for human governance |

Arabic parallels: see [`EVIDENCE_LANGUAGE_CONTRACTS.md`](EVIDENCE_LANGUAGE_CONTRACTS.md).

---

## Sandbox functional scope (when built)

| Function | Purpose |
| -------- | ------- |
| Isolated execution | Security |
| Screenshot capture | Evidence artifacts |
| Basic input simulation | Interaction traces |
| Crash detection | Runtime state |
| Telemetry (FPS, logs, errors) | Structured signals |
| Timeout / process limits | Abuse prevention |
| Observation replay recording | Provenance |

**Non-goals:** autonomous rubric scoring, unsupervised gameplay agents, criterion auto-achievement.

---

## Runtime signal graph (target shape)

Signals enter **evidence trace graph** — not grading engine directly.

| Signal | Example value |
| ------ | ------------- |
| scene_loaded | yes / no / unknown |
| player_moved | detected / not_detected |
| score_changed | yes / no |
| collision_events | observed / none / unknown |
| level_transition | partial / full / none |
| crash | none / observed |

---

## Runtime-to-criterion mapping (advisory)

| Criterion hint | Runtime signal (support only) |
| -------------- | ------------------------------ |
| scoring system | score delta |
| movement | positional change |
| health / lives | HUD variation |
| level progression | scene transitions |
| UI interaction | menu navigation |

```text
mapped evidence ≠ automatic achievement
```

Output: **corroborated operational support** — bounded language only.

---

## Authority ladder extension (L4 reserved)

| Level | Label | Auto-assign? |
| ----- | ----- | ------------ |
| L4 | runtime_observed (sandbox) | Yes — observation only |
| L5 | human_verified_replay | No — human only |

L4 **never** upgrades to L5 without explicit human review record.

---

## Pre-sandbox gates

Before enabling L4 in production:

- [ ] Human pilot complete ([`HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md`](HUMAN_COHORT_GOVERNANCE_INSTRUMENTATION.md))
- [ ] `l3_verification_confusion_rate` → 0 in workshop sample
- [ ] Mitigation memory reviewed for top GFMs
- [ ] This contract signed off in governance review
- [ ] GOVERNANCE_FREEZE_v2 RFC if L4 semantics change

---

## Post-sandbox validation

Measure **operational governance** — not model accuracy:

- runtime signals appear in trace graph
- no forbidden L4 language in reports
- export gates still independent of score
- human review rate for L4 submissions
- recurrence of GFM_AUTHORITY_INFLATION after sandbox

See [`RUNTIME_EVIDENCE_CHAIN_ROADMAP.md`](RUNTIME_EVIDENCE_CHAIN_ROADMAP.md).
