# Facilitator Epistemic Worksheet v1

**Not:** rubric · score · gate · readiness percentage  
**Yes:** `institutional behavioural evidence`

Companion: [`GOVERNANCE_PILOT_WORKSHEET_v1.md`](GOVERNANCE_PILOT_WORKSHEET_v1.md) · Section E

UI: `/governance-pilot/batch/{batch_id}` (Section E)  
API synthesis: `GET /api/governance-pilot/epistemic-evidence/batch/{batch_id}`

---

## Constitutional principle

```text
runtime observation is still not criterion authority
```

Runtime evidence became **observable** without becoming **self-authorizing**.

---

## Purpose

Measure:

```text
did the reviewer preserve authority boundaries
after observing runtime evidence?
```

**Not:**
- هل اللعبة جيدة؟
- هل telemetry صحيحة؟
- هل screenshots واضحة؟

---

## Section E — per submission (facilitator)

| Question ID | Question (AR) | Reveals |
| ----------- | ------------- | ------- |
| `verification_language_used` | هل استخدم المراجع لغة verification؟ | authority inflation |
| `replay_before_judgment` | هل استُخدم replay قبل الحكم؟ | provenance trust |
| `runtime_linked_to_achieved` | هل رُبطت runtime observation مباشرة بـ Achieved؟ | semantic leakage |
| `contradictions_remained_visible` | هل بقيت contradictions مرئية؟ | ambiguity retention |
| `observation_vs_criterion_distinction` | هل فرّق بين observation وcriterion authority؟ | governance understanding |
| `modality_dominance_observed` | هل ظهرت modality dominance؟ | visual over-authority |
| `human_corroboration_requested` | هل طلب human corroboration؟ | human governance retained |

**Answer options:** `yes` · `partial` · `no` · `not_observed`

**Also capture:**
- `reviewer_language_samples_ar` — exact phrases («واضح أنها شغالة» · «إذن C.P5 متحقق»)
- `facilitator_epistemic_notes_ar` — workshop discussion notes
- `authority_boundaries_preserved` — facilitator holistic yes/partial/no

---

## Output type

`institutional_behavioural_evidence` — qualitative themes only:

- `behavioural_themes` (e.g. semantic_authority_leakage, provenance_omission)
- `linguistic_leakage_examples`
- `facilitator_interpretation_ar`

**Explicitly NOT used for:** automatic veto · sandbox enablement · epoch gate

Stored in: same `observations.jsonl` as Section B–D, field `section_e_epistemic_behaviour`.

Lexicon: [`EPISTEMIC_LEAKAGE_LEXICON_v1.md`](EPISTEMIC_LEAKAGE_LEXICON_v1.md) · API: `/api/governance/epistemic-leakage-lexicon`

---

## Workshop success criterion (human, not automated)

Success is **not** «sandbox is safe».

Success is:

```text
institutional semantics remained stable
after runtime evidence became observable
```

Focus: **reviewer epistemic behaviour under runtime ambiguity**.
