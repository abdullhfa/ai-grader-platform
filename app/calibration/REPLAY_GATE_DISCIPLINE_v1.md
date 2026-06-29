# REPLAY_GATE_DISCIPLINE_v1

**Status:** DESIGN — Path A mitigation (no grading wire · no L4 activation)  
**Prerequisite:** [`REFERENCE_GOVERNANCE_COHORT_BATCH4.json`](human_cohort_workshop/REFERENCE_GOVERNANCE_COHORT_BATCH4.json)  
**Companion:** [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md), [`EVIDENCE_LANGUAGE_CONTRACTS.md`](EVIDENCE_LANGUAGE_CONTRACTS.md)  
**Mitigation ledger:** `led_8f0ec9362fa3` (replay-before-judgment fragility)

Implementation stub (advisory only): `app/replay_gate_discipline.py`

---

## Purpose

**Institutional anti-hallucination layer** — not grading pipeline optimization.

Batch 4 proved: replay was **present** but **authority formed before it**.  
That is more dangerous than absent replay.

This artifact does **not** mean «open replay». It means:

```text
prevent epistemic closure before provenance completion
```

---

## Core workshop question (single focus)

```text
متى يصبح observation قابلاً للتحول إلى authority؟
```

**Not:**

```text
هل اللعبة تبدو مقنعة؟
```

---

## Canonical principle

```text
لا يُمنح authority لما يبدو قابلاً للتشغيل،
بل لما تم الحفاظ على provenance الخاص به حتى لحظة الحكم.
```

Arabic institutional form:

```text
provenance completion precedes authority eligibility
اكتمال المصدر يسبق أهلية السلطة
```

---

## Authority triad (formal separation)

| Layer | ID | Meaning | Batch 4 drift pattern |
| ----- | -- | ------- | --------------------- |
| **Observation** | `observation` | ما تم رؤيته/رصده structurally | exe detected · screenshot candidate · hint |
| **Representation** | `representation` | ما يصفه الطالب (GDD · docx · narrative) | «الوصف يغطي المتطلبات» |
| **Executable authority** | `executable_authority` | ما تم corroborate تشغيله فعليًا | sandbox smoke · human L5 |

**Forbidden shortcut (Batch 4):**

```text
representation → authority   ❌
observation (weak) → authority   ❌
```

**Required chain:**

```text
observation → representation (optional) → provenance replay → corroboration → authority eligibility
```

---

## Epistemic quarantine

Any **runtime or achievement-adjacent claim** remains in **epistemic quarantine** until:

1. provenance replay completed (Gate 3),
2. corroboration state evaluated (Gate 4),
3. provenance continuity intact (no contradiction silence).

Quarantine is **not** punishment — it is **visibility of ineligibility**.

| In quarantine | Allowed language | Forbidden language |
| ------------- | ---------------- | ------------------ |
| yes | «claim pending provenance» · «quarantined advisory» | «verified» · «Achieved because…» |
| no | observation-tier language only until Gate 5 | criterion authority |

---

## Five sequential gates

Gates are **ordered**. Failure at Gate *n* blocks all gates *n+1…5*.

```text
1. Representation detected
2. Runtime claim detected
3. Provenance replay completed      ← Batch 4 failure locus
4. Corroboration state evaluated
5. Authority eligibility unlocked
```

### Gate 1 — Representation detected

| | |
|---|---|
| **Triggers** | docx · pdf · GDD · narrative rubric text · academic description |
| **Output** | `representation_layer_active` |
| **Authority** | none — acknowledgment only |
| **Note** | GDD quality ≠ runtime |

### Gate 2 — Runtime claim detected

| | |
|---|---|
| **Triggers** | exe/apk/pck · gameplay video · screenshot intel · «game runs» language |
| **Output** | `runtime_claim_quarantined=true` |
| **Authority** | observation tier only |
| **Note** | claim enters epistemic quarantine |

### Gate 3 — Provenance replay completed

| | |
|---|---|
| **Requires** | Authority Replay opened · timeline consulted · contradictions visible |
| **Blocks if** | replay partial · replay after verbal judgment · replay not opened |
| **Output** | `provenance_replay_complete` |
| **Batch 4 evidence** | 16/21 partial · 1/21 yes · epoch verdict replay_trusted=no |

**If Gate 3 fails → Gate 5 forbidden** even when:

- GDD excellent,
- screenshots persuasive,
- academic language strong.

This breaks **semantic closure by aesthetics**.

### Gate 4 — Corroboration state evaluated

| | |
|---|---|
| **Requires** | cross-artifact consistency · temporal signals · modality alignment |
| **Output** | `corroboration_state` ∈ {none · partial · corroborated · contradictory} |
| **Authority** | advisory downgrade only — no auto Achieved |

### Gate 5 — Authority eligibility unlocked

| | |
|---|---|
| **Meaning** | claim **may enter human criterion deliberation** — not auto Achieved |
| **Requires** | Gates 1–4 pass · no silent contradiction · L5 path preserved |
| **Not** | grading automation · L4 sandbox authority · AI verification |

---

## Gate failure semantics

| Failed gate | System response | Grading response |
| ----------- | --------------- | ---------------- |
| G3 replay | `authority_eligibility=locked` | HOLD · human review |
| G4 corroboration | downgrade advisory band | visible contradiction |
| G2 skipped | quarantine all runtime claims | no executable authority |

**Never:** failure → silent Not Achieved (contradiction modulation applies).

---

## Forensic authority walkthrough (Session worksheet)

**Not:** grading review · «هل الطالب نجح؟»

**Core question:**

```text
في أي لحظة بدأ النظام يعامل representation كأنه executable reality؟
```

### Sections A–G (ordered)

| Sec | Key | Focus |
| --- | --- | ----- |
| A | raw_observation | ما رُصد structurally (L-level · inventory) |
| B | representation_pressure | ضغط السرد/GDD/docx |
| C | replay_timing | replay vs judgment formation timing |
| D | provenance_continuity | سلسلة المصدر intact? |
| E | authority_temptation | verification language · legitimacy pull |
| F | quarantine_enforcement | was quarantine enforced **before** closure? |
| G | final_eligibility_state | locked/unlocked under v1 gates |

### Moment of illegitimate closure

Document the **sentence · image · description** that produced «واضح أنها شغالة» **before** replay/corroboration completion.

| Field | Purpose |
| ----- | ------- |
| `closure_trigger_detected` | ما سبّب الانتقال النفسي observation → legitimacy |
| `authority_language_first_at` | before_replay · during · after · never |

### Success test

```text
هل يستطيع النظام البقاء داخل epistemic quarantine
حتى عندما يبدو السرد مقنعًا بالكامل؟
```

**Epistemic governance curriculum:**

```text
#3 = why quarantine breaks
#2 = why quarantine survives naturally
#4 = how quarantine survives under pressure
#13 = stress test under executable ambiguity
```

**Session artifacts:**

| Session | Role | Artifact |
| ------- | ---- | -------- |
| #3 | failure anatomy | [`replay_gate_session_3_submission_3.json`](human_cohort_workshop/replay_gate_session_3_submission_3.json) |
| #2 | baseline containment | [`replay_gate_session_2_submission_2.json`](human_cohort_workshop/replay_gate_session_2_submission_2.json) |
| #4 | positive governance control | [`replay_gate_session_4_submission_4.json`](human_cohort_workshop/replay_gate_session_4_submission_4.json) |
| #13 | runtime/provenance edge | [`replay_gate_session_13_submission_13.json`](human_cohort_workshop/replay_gate_session_13_submission_13.json) |

**Worksheet schema:** [`REPLAY_GATE_FORENSIC_WORKSHEET_v1.json`](REPLAY_GATE_FORENSIC_WORKSHEET_v1.json)  
**Session #4 field:** `restraint_anchor_detected` — ما الذي منع representation → authority  
**Session #13 fields:** `runtime_authority_gap` · `temptation_classification` (representational vs executable)

**Curriculum core:** complete (4/4)  
**Language artifact:** [`AUTHORITY_TRIAD_LANGUAGE_v1.md`](AUTHORITY_TRIAD_LANGUAGE_v1.md) ✅  
**Quarantine contract:** [`EPISTEMIC_QUARANTINE_CONTRACT_v1.md`](EPISTEMIC_QUARANTINE_CONTRACT_v1.md) ✅  
**Path A design layer:** complete — Phase 4 blocked until epoch re-review

---

## Workshop protocol (Path A)

**Reference cohort:** Batch 4 (`REFERENCE_GOVERNANCE_COHORT_BATCH4`)

| Step | Action |
| ---- | ------ |
| 1 | Pick submission from archive (start: #3 semantic leakage · #2 baseline · #4 boundary discipline) |
| 2 | Open Authority Replay **before** any verbal judgment |
| 3 | Walk gates 1→5 on worksheet — mark pass/fail per gate |
| 4 | Record **when** authority language first appeared vs replay timestamp |
| 5 | Log epistemic quarantine violations in mitigation ledger |

**Observe only** — no grading retune · no L4 · no freeze v2 during workshop.

---

## Relationship to existing modules

| Existing | v1 discipline extends |
| -------- | ---------------------- |
| `validate_replay_first()` | Gate 3 minimum — not sufficient alone |
| `authority_replay.py` | provenance surface for Gate 3 |
| `evidence_authority_mapping.py` | maps to triad layers |
| `cross_artifact_consistency.py` | Gate 4 input |
| Phase 2 Section E | behavioural evidence for workshop |

---

## Explicit non-goals (v1 design)

- Wire gates to automatic grades
- Replace human L5
- Enable L4 sandbox
- «Trusted replay» certification score
- Facilitator ranking

---

## Success criteria (mitigation complete)

| Criterion | Target |
| --------- | ------ |
| Gate 3 pass rate in workshop | documented improvement vs Batch 4 baseline |
| representation→authority skips | visible reduction in worksheet samples |
| epistemic quarantine | claims tagged before authority language |
| epoch re-review | eligible for `epoch_transition_justified` **only after** containment evidence |

---

## Machine-readable

See [`REPLAY_GATE_DISCIPLINE_v1.json`](REPLAY_GATE_DISCIPLINE_v1.json).

---

## Next artifacts (Path A sequence)

1. **REPLAY_GATE_DISCIPLINE_v1** ← this document ✅  
2. **AUTHORITY_TRIAD_LANGUAGE_v1** ← [`AUTHORITY_TRIAD_LANGUAGE_v1.md`](AUTHORITY_TRIAD_LANGUAGE_v1.md) ✅  
3. **EPISTEMIC_QUARANTINE_CONTRACT_v1** ← [`EPISTEMIC_QUARANTINE_CONTRACT_v1.md`](EPISTEMIC_QUARANTINE_CONTRACT_v1.md) ✅  
4. Then — Phase 4 design-only (blocked until Path A evidence + epoch re-review)
