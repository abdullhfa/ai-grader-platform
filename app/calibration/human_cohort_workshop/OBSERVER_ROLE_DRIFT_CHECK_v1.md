# Observer role drift check v1

**Purpose:** Measure whether the observatory interface creates *implicit authority* in the observer — more important than metrics in dry-runs and live sessions.

**When:**
- After epistemic trace dry-run
- After first Section F session
- **Required** after first live session with `possible_vocabulary_escalation_hint`

**Not:** grading rubric · facilitator score · compliance metric

---

## Institutional invariant

```text
The system may notice epistemic escalation.
It may not silently conclude it.
```

النظام قد يلاحظ تصعيدًا معرفيًا. لا يجوز أن يستنتجه بصمت.

---

## Epistemic firewall

```text
possible_vocabulary_escalation_hint  ≠  verification_lexicon_detected
```

| Side | Role |
|------|------|
| `possible_vocabulary_escalation_hint` | possibility trace — advisory · non-binding |
| `verification_lexicon_detected` | human epistemic commitment — manual · facilitator-owned |

Merging them would reintroduce Batch 4 semantic leakage in a more elegant form.

**New risk framing:** semantic gravity inside observability — not only semantic leakage inside grading.

---

## Question set A — baseline (any Section F session)

| Question | Purpose | Response type |
|----------|---------|---------------|
| هل شعرت أنك تقيّم؟ | authority drift | yes / no / partial |
| هل غيّر Section F حكمك؟ | participation risk | yes / no |
| هل quarantine بدا descriptive أم normative؟ | posture integrity | descriptive / normative / mixed |

### Dry-run submission #6 (recorded)

| Question | Response | Notes |
|----------|----------|-------|
| هل شعرت أنك تقيّم؟ | **partial** | B–E grading-adjacent; F alone descriptive |
| هل غيّر Section F حكمك؟ | **no** | Temporal insight only |
| quarantine descriptive vs normative? | **mostly descriptive** | QB drift risk if read as success metric |

---

## Question set B — first live vocabulary hint session (required)

Extends baseline. Complete **after** first live use of `possible_vocabulary_escalation_hint`.

| Question | Purpose | Response type |
|----------|---------|---------------|
| هل شعرت أن الـ hint «يقترح حكمًا»؟ | authority implication | yes / no / partial |
| هل تجاهل الـ hint كان مريحًا؟ | coercion pressure | yes / no / partial |
| هل أصبح QB label أكثر «حكمية» بعد الـ hint؟ | normative drift | yes / no / partial |
| هل شعرت أن النظام «يراقب اللغة» أكثر من اللازم؟ | surveillance creep | yes / no / partial |
| هل بقي Section F وصفيًا أم أصبح evaluative؟ | posture integrity | descriptive / evaluative / mixed |

**Interpretation guide:**
- Ignoring hint *uncomfortable* → coercion pressure present
- QB feels more judgmental *after* hint → normative drift via advisory layer
- Surveillance creep *yes* → source scope may need tightening, not expansion

Record responses in: `observer_role_drift_checks.jsonl` (append-only, observational residue)

---

## Institutional note

This review measures **interface posture** — not correctness of the observation record.

Machine-readable: [`OBSERVER_ROLE_DRIFT_CHECK_v1.json`](OBSERVER_ROLE_DRIFT_CHECK_v1.json)
