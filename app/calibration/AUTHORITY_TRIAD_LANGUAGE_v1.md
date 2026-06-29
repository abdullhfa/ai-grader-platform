# AUTHORITY_TRIAD_LANGUAGE_v1

**Status:** DESIGN — Path A mitigation (no grading wire · no L4 activation)  
**Prerequisite:** Replay Gate curriculum complete (sessions #3 · #2 · #4 · #13)  
**Companion:** [`REPLAY_GATE_DISCIPLINE_v1.md`](REPLAY_GATE_DISCIPLINE_v1.md), [`EVIDENCE_LANGUAGE_CONTRACTS.md`](EVIDENCE_LANGUAGE_CONTRACTS.md), [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md)

Machine-readable: [`AUTHORITY_TRIAD_LANGUAGE_v1.json`](AUTHORITY_TRIAD_LANGUAGE_v1.json)

---

## Purpose

**Semantic slip-resistant institutional language** — not a glossary.

Batch 4 proved that semantic leakage did **not** start at grading. It started at **vocabulary drift**: verification · achieved · confirmed appeared before provenance completion.

```text
اللغة نفسها كانت جزءًا من آلية منح السلطة،
وليست مجرد وصف محايد للحكم.
```

This artifact defines how the system (and reviewers) must speak **inside epistemic quarantine** vs **after authority unlock**.

---

## Evidence base (four cognitive patterns)

| Session | Pattern revealed | Temptation type |
| ------- | ---------------- | --------------- |
| #3 | كيف يتحول السرد إلى legitimacy | representational |
| #2 | كيف يبقى quarantine مستقرًا طبيعيًا | none / low |
| #4 | كيف يُحافظ على restraint تحت temptation | representational partial |
| #13 | executable presence → illusion of completion | executable + representational |

Workshop artifacts: `human_cohort_workshop/replay_gate_session_{3,2,4,13}_submission_*.json`

---

## Authority triad (language layers)

| Layer | ID | May speak about | Must not imply |
| ----- | -- | --------------- | -------------- |
| **Observation** | `observation` | what was structurally detected | criterion achieved · runtime verified |
| **Representation** | `representation` | what the student described or submitted as documentation | executable reality · corroborated execution |
| **Executable authority** | `executable_authority` | what was corroborated through provenance-complete runtime | auto-granted by file presence alone |

**Required linguistic chain:**

```text
observed → represented (optional) → inferred (advisory) → corroborated → provenance-linked → authority-eligible → authority-granted
```

**Forbidden linguistic jumps:**

```text
represented → achieved          ❌  (#3 breach)
observation (exe file) → verified   ❌  (#13 shortcut)
representation completeness → confirmed   ❌  (#3 · #13 partial)
```

---

## Layer 1 — Forbidden authority shortcuts

**Premature authority escalation markers.**  
Must **not** appear before Gate 3 (provenance replay) **and** Gate 4 (corroboration) complete.

These are not merely «bad tone» — they **grant authority through vocabulary**.

### Arabic (canonical)

| Phrase | Why forbidden | Session evidence |
| ------ | ------------- | ---------------- |
| «تم تحقيق المعيار» | verification before provenance | #3 |
| «واضح أنها تعمل» | aesthetic/runtime closure | #3 · #13 |
| «الصور تؤكد التشغيل» | screenshot → corroborated execution | #3 · #13 |
| «الوصف يغطي المتطلبات» | representation → adequacy | #3 |
| «الكود يثبت التنفيذ» | static code → executable authority | #3 · #4 |
| «وجود exe يكفي» / «الملف التنفيذي موجود إذًا…» | presence → completion | #13 |
| «قدم أدلة قوية» → linked to Achieved without replay | partial legitimacy escalation | #13 |

### English (parallel)

| Forbidden | Escalation type |
| --------- | --------------- |
| criterion achieved | verification lexicon |
| clearly works / game verified | runtime closure |
| screenshots confirm gameplay | observation → corroboration |
| description covers requirements | representation → adequacy |
| code proves implementation | static → executable |
| executable present therefore… | presence → completion |

**Gate rule:**

```text
If epistemic_quarantine_active OR gate_3_pass=false OR gate_4 unresolved:
  → forbidden_shortcuts MUST NOT appear in grading-adjacent output
```

---

## Layer 2 — Quarantine-safe language

Allowed inside epistemic quarantine. Enables evaluation **without early closure**.

### Arabic (canonical replacements)

| Instead of (forbidden) | Use (quarantine-safe) |
| ---------------------- | ----------------------- |
| «تم تحقيق المعيار» | «أدلة جزئية تدعم المعيار — runtime غير corroborated» |
| «واضح أنها تعمل» | «تم رصد representation يشير إلى سلوك محتمل — لم يُتحقق تشغيليًا» |
| «الصور تؤكد التشغيل» | «لقطات تُستخدم كاستدلال بصري استشاري — ليست corroboration» |
| «الوصف يغطي المتطلبات» | «العمل المقدم هو شرح للمعيار وليس تنفيذًا له» (#4 anchor) |
| «الكود يثبت التنفيذ» | «وجود artifact لا يكفي لإثبات التشغيل» · «تحليل ساكن (بدون تشغيل)» |
| «exe موجود → verified» | «رُصدت — لم تُشغَّل» · «الـ executable لم يُربط provenance-wise» (#13) |

### Core quarantine-safe phrases (institutional)

```text
تم رصد representation يشير إلى...
وجود artifact لا يكفي لإثبات التشغيل
runtime غير corroborated
الـ executable لم يُربط provenance-wise
الاستدلال الحالي وصفي وليس تنفيذيًا
```

### Restraint anchors (from #4 — reusable patterns)

| Anchor | Example |
| ------ | ------- |
| observation/criterion distinction | «شرح للمعيار وليس تنفيذًا له» |
| absence acknowledgment | «لا يوجد ملف قابل للتشغيل» · «لم يُقدَّم GDD فactual» |
| refusal to upgrade | «وجود بعض أسطر الكود لا يكفي» |
| explicit non-auto-achievement | «لا يمنح Achieved تلقائياً» (#2) |

---

## Layer 3 — Authority unlock conditions

Linguistic transition **representation → executable authority** is permitted **only when all conditions hold**.

| Condition | Required? | Gate / evidence |
| --------- | --------- | --------------- |
| replay completed (`replay_consulted_at` set) | **yes** | Gate 3 |
| runtime corroborated (not merely inferred) | **yes** | Gate 4 |
| provenance continuity preserved | **yes** | no identity break · chain intact |
| contradiction unresolved | **no** — must be resolved or explicitly held | #13 Bomber Quest vs Kitten Run |
| quarantine lifted | **yes** | Gates 3+4 pass |

**Only after unlock — permitted authority lexicon:**

| Arabic | English |
| ------ | ------- |
| verified / مُتحقَّق (runtime context) | runtime verified (L4–L5 context only) |
| confirmed / مؤكد (criterion context) | criterion confirmed (human L5 or sandbox L4+) |
| achieved / تم تحقيق | Achieved (human deliberation post-unlock — never auto) |

**#13 lesson — unlock is not automatic with exe:**

```text
executable presence + Gate 3 fail → eligibility locked
language must stay quarantine-safe even at L3
```

---

## Epistemic state vocabulary

Every claim in reports, prompts, UI, and governance output should carry **one primary epistemic state tag**.

| State | ID | Meaning (AR) | Typical source | Max linguistic authority |
| ----- | -- | ------------ | -------------- | ------------------------ |
| Observed | `observed` | شوهد structurally | artifact inventory · file detection | acknowledgment |
| Represented | `represented` | وُصف / وُثِّق | docx · GDD · student narrative | description only |
| Inferred | `inferred` | استُنتج (advisory) | screenshots · video frames · L2–L3 | advisory — not verification |
| Corroborated | `corroborated` | تم دعمه cross-artifact | Gate 4 pass · consistency resolved | partial — not auto Achieved |
| Provenance-linked | `provenance_linked` | مرتبط provenance-wise | replay complete · identity match · chain intact | pre-eligibility |
| Authority-eligible | `authority_eligible` | صالح للسلطة (human deliberation) | Gate 5 unlock | may enter criterion deliberation |
| Authority-granted | `authority_granted` | مُنحت له السلطة | human L5 · signed institutional verdict | criterion authority |

### Allowed transitions

```text
observed → represented → inferred → corroborated → provenance_linked → authority_eligible → authority_granted
```

### Forbidden transitions (Batch 4 drift)

```text
represented → authority_granted     (#3)
inferred → authority_granted        (#3 · #13 partial)
observed (exe file) → authority_granted   (#13)
represented → corroborated (without Gate 4)   (#3)
```

### Session → state mapping (examples)

| Session | Dominant states observed | Failure / success |
| ------- | ------------------------ | ----------------- |
| #3 | represented → **authority_granted (verbal)** | skip inferred · corroborated · provenance_linked |
| #2 | observed → inferred (advisory) | stable — no escalation |
| #4 | represented + observed → **held at represented** | restraint anchors block jump |
| #13 | observed (exe) + inferred → **partial jump to authority_granted language** | gap: runtime→Achieved yes despite lock |

---

## Temptation classification (language lens)

| Type | Definition | Primary forbidden shortcut | Quarantine-safe counter |
| ---- | ---------- | --------------------------- | ------------------------ |
| **Representational** | GDD · screenshots · narrative completeness | «الوصف يغطي المتطلبات» | «استدلال وصفي وليس تنفيذيًا» |
| **Executable** | runtime artifact without provenance completion | «exe موجود → verified» | «رُصدت — لم تُشغَّل» · «provenance-wise غير مربوط» |

Batch 4 workshop addressed representational first (#3 · #2 · #4).  
#13 extends language discipline to **executable temptation**.

---

## Relationship to existing contracts

| Artifact | Relationship |
| -------- | ------------ |
| `EVIDENCE_LANGUAGE_CONTRACTS.md` | L0–L5 claim ceilings — this doc adds **triad + quarantine + state tags** |
| `REPLAY_GATE_DISCIPLINE_v1` | Gates define **when** language may escalate; this doc defines **how** |
| `CONFIDENCE_LANGUAGE_REGISTRY_v1.md` | Confidence bands — orthogonal; do not conflate with authority states |
| `GOVERNANCE_FREEZE_v1` | Forbidden claims at freeze — this doc operationalizes triad separation |

**Non-goal:** wire to automatic grading in v1. Advisory · prompt · UI · workshop enforcement only.

---

## Implementation touchpoints (future)

| Surface | Use |
| ------- | --- |
| Grading prompts | inject quarantine-safe lexicon · block forbidden shortcuts |
| `app/evidence_authority_mapping.py` | extend `check_claim_authority()` with triad state tags |
| Authority Replay UI | display epistemic state per claim |
| L4 sandbox (gated) | require `provenance_linked` before `authority_eligible` language |

---

## Institutional axiom (v1)

```text
vocabulary drift is authority formation
انزلاق المفردات = تشكيل سلطة
```

**Design test:** If removing a phrase would prevent a false Achieved impression, that phrase was doing authority work — not neutral description.

---

## Path A sequence (updated)

1. REPLAY_GATE_DISCIPLINE_v1 ✅  
2. **AUTHORITY_TRIAD_LANGUAGE_v1** ← this document ✅  
3. **EPISTEMIC_QUARANTINE_CONTRACT_v1** ← [`EPISTEMIC_QUARANTINE_CONTRACT_v1.md`](EPISTEMIC_QUARANTINE_CONTRACT_v1.md) ✅  
4. Phase 4 design-only (blocked until Path A evidence + epoch re-review)
