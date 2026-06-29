# Evidence Language Contracts

Companion to [`EVIDENCE_GOVERNANCE_ROADMAP.md`](EVIDENCE_GOVERNANCE_ROADMAP.md), [`GOVERNANCE_POSITIONING.md`](GOVERNANCE_POSITIONING.md), [`AUTHORITY_TRIAD_LANGUAGE_v1.md`](AUTHORITY_TRIAD_LANGUAGE_v1.md), and [`EPISTEMIC_QUARANTINE_CONTRACT_v1.md`](EPISTEMIC_QUARANTINE_CONTRACT_v1.md).

Canonical institutional phrasing for reports, PDFs, Word exports, prompts, and reviewer UI.

---

## Core rule

```text
ingestion semantics ≠ grading authority
runtime observation ≠ criterion authority
```

Every claim must map to an **evidence type** and a **runtime_evidence_level (L0–L5)** ceiling.

Implementation: `app/evidence_authority_mapping.py` — `check_claim_authority()`, `sanitize_claim_text()`.

---

## Forbidden → Allowed (English)

| Forbidden (never unless L4–L5 verified) | Allowed replacement |
| --------------------------------------- | ------------------- |
| game verified | gameplay evidence observed / runtime-capable artifact detected |
| gameplay confirmed | gameplay visually inferred (advisory) |
| criterion confirmed | evidence partially supports |
| game works | runtime-capable artifact detected — not executed |
| testing completed | testing evidence submitted |
| runtime behaviour verified | runtime behaviour inferred from available evidence |
| criterion operationally confirmed | documentation and static evidence analyzed — runtime unavailable |

---

## Forbidden → Allowed (Arabic)

| ممنوع | مسموح |
| ----- | ----- |
| اللعبة تعمل وتحقق المعيار | artifact تنفيذي مُرصد — لم يُتحقق من التشغيل |
| تم التحقق من التشغيل | لم يُتحقق من التشغيل — استدلال استشاري فقط |
| المعيار مؤكد | أدلة جزئية تدعم المعيار |
| اختبار مكتمل | أدلة اختبار مُقدَّمة — بدون runtime verification |
| اللعبة مُتحقَّقة | gameplay evidence observed (advisory) |

---

## Evidence type → Allowed claims

| Evidence Type | Max Level | Allowed Claims |
| ------------- | --------- | -------------- |
| `.exe` / `.apk` detected | L1 | runtime-capable artifact exists; executable submitted not executed |
| HUD screenshot (Vision advisory) | L2 | possible scoring mechanic; possible UI/HUD |
| Gameplay video (not analyzed) | L3 | inferred gameplay activity (advisory) |
| Source code inspection | L2 | implementation candidate; code inspected without execution |
| Documentation | L2 | design analyzed; evidence partially supports |
| Runtime sandbox (future) | L4 | limited runtime observations collected |
| Human review | L5 | authoritative confirmation |

Claims exceeding `max_level` for the active evidence type are **blocked** (`check_claim_authority`).

---

## Gameplay video (L3 — temporal advisory)

| Forbidden | Allowed |
| --------- | ------- |
| gameplay verified | gameplay activity inferred |
| game completed | gameplay footage candidate |
| mechanic confirmed | mechanic visually suggested |
| runtime validated | runtime hints observed |

Module: `app/gameplay_video_inference.py` — frame sampling, scene-change heuristics, HUD band stability, cross-artifact corroboration.

**temporal_evidence_authority** is distinct from static screenshot authority. Max auto level remains **L3**.

Module: `app/temporal_consistency_governance.py` — cross-temporal contradiction signals → `claim_authority_flags.temporal_consistency` (not grading).

Module: `app/evidence_trace_graph.py` — `artifact → hint → corroboration → authority → claim_boundary`.

---

## Cross-artifact consistency language

When `cross_artifact_consistency` flags fire:

| Use | Do not use |
| --- | ---------- |
| consistency ambiguity between artifacts | student lied / cheating (automatic) |
| engine signals conflict — corroboration required | wrong engine → automatic Not Achieved |
| multiple build names — linkage unclear | assume all builds equivalent |

Implementation: `app/cross_artifact_consistency.py`.

---

## Module touchpoints

| Surface | Contract enforcement |
| ------- | -------------------- |
| AI system prompt | `batch_grader.py` — game dev + artifact governance blocks |
| Grading text injection | `format_authority_mapping_for_grading()` |
| Coverage notice | `build_grading_coverage_notice()` |
| PDF report | `report_generator.py` — evidence matrix |
| Word export | `main.py` — coverage + matrix |
| Post-grade sanity (optional) | `sanitize_claim_text()` on criterion reasoning |

---

## Change control

When changing prompts, models, or report templates:

1. Check this file first.
2. Run claim samples through `check_claim_authority()`.
3. Do not introduce «verified» / «confirmed» without L4+ evidence path.

---

## Non-goals

- Auto-replace AI criterion verdicts based on language alone (sanitization is advisory for now).
- Treat language compliance as equivalent to human review (L5).
