# Evidence Governance Roadmap

Companion to [`GOVERNANCE_POSITIONING.md`](GOVERNANCE_POSITIONING.md).

This document defines **claim-boundary governance** — not feature backlog for a “grader pipeline.”

---

## Core distinction (canonical)

```text
ingestion semantics ≠ grading authority
```

| Fallacy (avoid) | Correct chain |
| ----------------- | ------------- |
| `file ingested` → `evidence understood` → `grading authority` | `artifact available` → `candidate detected` → `corroborated` → `authority may escalate` → else `advisory` / `HOLD` |

**Non-goal:** silent upgrade from “uploaded” to “verified.”

---

## What the system must ask

Not only:

```text
what could we parse?
```

But:

```text
what do we have institutional legitimacy to claim we analyzed?
```

Success metric:

```text
structured epistemic visibility
```

**Claim boundaries before grades** — uncertainty must not hide inside percentages or positive narrative alone.

---

## Evidence-governed authority escalation

| Stage | Meaning | Typical output language |
| ----- | ------- | ------------------------ |
| `artifact_available` | File on disk / in submission bundle | “وُجد ملف …” |
| `candidate_detected` | Path/name/profile suggests evidence type | “مرشّح أدلة …” |
| `analyzed` | Model or parser consumed content under defined scope | “تم تحليل …” |
| `corroborated` | Multiple modalities align with bounded confidence | “مُؤيَّد جزئياً …” |
| `runtime_verified` | Executable ran, replay checked, or telemetry confirmed | “تم التحقق من التشغيل …” |
| `unresolved_ambiguity` | Cross-artifact conflict or insufficient proof | `HOLD` / advisory / explicit gap |

This is **authority escalation**, not multimodal parsing for its own sake.

---

## Canonical assessment language (institutional semantic contracts)

These phrases must appear in **reports, PDFs, Word exports, and reviewer UI** — not only in prompts.

| Use | Do not use (unless verified) |
| --- | --------------------------- |
| `runtime behaviour inferred from available evidence` | `game verified` |
| `code inspected without execution` | `game tested` |
| `screenshot analyzed as advisory candidate` | `gameplay confirmed` |
| `consistency ambiguity between artifacts` | `student error` (as automatic verdict) |
| `embedded document evidence analyzed` | `full submission understood` |

Arabic equivalents should stay parallel in `build_grading_coverage_notice` and report templates.

---

## Expansion map (module-linked)

| # | Expansion | Authority level | Primary module(s) | Governance constraint | Non-goals |
| - | ----------- | ----------------- | ------------------- | --------------------- | --------- |
| **1** | Standalone screenshot intelligence | **advisory candidate** | `project_profile.py` (`_RUNTIME_FOLDER_MARKERS`, `_path_suggests_runtime_screenshot`), future `advisory_screenshot_lane.py` | Vision may describe; **must not** alone raise criterion to achieved | Treat folder PNG as Word-embedded proof |
| **2** | Runtime evidence classification | **inferred hints** | `project_profile.py`, `evidence_schema.py`, `cross_modal_corroboration.py` | Classify `.exe`, video frames, logs; label `inferred` | Claim verified runtime without run |
| **3** | Cross-artifact consistency engine | **ambiguity signal** | `cross_artifact_consistency.py` | Emit `consistency_ambiguity` (Godot vs Unity vs title) | Auto-penalize as “lying” |
| **3b** | Gameplay video inference (L3) | **temporal advisory** | `gameplay_video_inference.py` | Frame sampling + temporal hints + corroboration | Vision narrative / gameplay verified |
| **4** | Evidence coverage reporting | **explainability** | `batch_grader.py` → `build_grading_coverage_notice`, `report_generator.py` | Structured table: type × coverage × authority | Hide gaps in prose only |
| **5** | Evidence sufficiency map | **advisory per criterion** | `rubric_sufficiency_contracts.py`, `human_review_gates.py` | Map criterion → evidence status; **no wire to achieved** | Shadow sufficiency → auto grade |

---

## Current implementation baseline (as of roadmap v1)

| Capability | Status | Notes |
| ---------- | ------ | ----- |
| Boundary honesty in reports | **partial — live** | `grading_coverage_notice` in batch grading snapshot + PDF/Word section «نطاق التصحيح الآلي» |
| Embedded Word/PDF images | **analyzed** | Vision on extracted embedded images |
| Folder / standalone PNG | **ingested, not vision-graded** | Declared explicitly (e.g. 17 images not used — محمد عكاوي case) |
| Screenshot path semantics | **detection only** | `screenshots`, `سكرينات`, `gameplay`, etc. in `project_profile` |
| Code inspection | **analyzed, non-runtime** | `build_dual_version_grading_addon`, Unity/Godot hints |
| Cross-artifact conflict | **structured signal** | `cross_artifact_consistency.py` + `artifact_inventory` |
| Evidence authority mapping | **live** | `evidence_authority_mapping.py` — allowed/forbidden claims |
| Language contracts | **documented** | `EVIDENCE_LANGUAGE_CONTRACTS.md` |
| Sufficiency → achieved | **forbidden** | `human_review_gates`: `governance_signal_only` |

Reference case proving maturity direction:

```text
تقرير_الالعاب محمد عكاوي — transparency + boundary honesty + corroboration awareness
```

---

## Phase priority (now)

Do **not** expand with “better grading prompts” first.

Expand:

```text
evidence ingestion governance
```

### Priority A — (1) Standalone screenshot intelligence

**Lane:** `advisory evidence lane` only.

**Behaviour:**

1. Detect images under semantic folders (`screenshots`, `testing`, `gameplay`, `evidence`, `سكرينات`, …).
2. Optional capped Vision pass (e.g. max N images) tagged `advisory_screenshot`.
3. Store in `grading_snapshot` / trace — **not** merged as authoritative criterion proof.
4. Coverage report links: `detected` → `advisory_analyzed` | `not_analyzed`.

**Review requirement:** human reviewer may promote; system must not.

### Priority B — (4) Evidence coverage reporting

**Behaviour:**

Replace prose-only gaps with a fixed table in reports:

| Evidence type | Coverage | Authority |
| ------------- | -------- | --------- |
| Embedded screenshots | analyzed / failed / skipped | analyzed |
| Folder screenshots | not analyzed / advisory only | advisory |
| Source code | partial / full read | inspected non-runtime |
| Executable | present / not run | unavailable |
| Gameplay video | frames extracted | inferred |
| Testing (forms/surveys) | document text | document-supported |

**Module touchpoints:** extend `build_grading_coverage_notice` → structured `evidence_coverage_matrix`; render in `report_generator.py` + Word export in `main.py`.

Together, (1)+(4) resolve:

```text
visible evidence scope ambiguity
```

Without raising authority (no silent creep).

---

## Deferred (explicitly later)

- Executable launch / replay verification
- Autonomous “whole game understood”
- Sufficiency engine wired to achieved grades
- Full `artifact_consistency_graph` as blocking gate

---

## Anti-pattern: silent authority creep

Watch for:

```text
file ingested = evidence understood = grading authority
```

Engineering checks:

- New modality → default authority = `advisory` unless workshop + freeze says otherwise.
- Any new “analyzed” flag → must appear in coverage matrix.
- Prompt changes alone **cannot** upgrade authority tier.

---

## Target category (12–18 month horizon)

```text
institutionally bounded evidence interpretation infrastructure
```

Not:

```text
AI grading engine
```

---

## Ordered engineering sequence (after workshop signal)

```text
workshop complete → governance_signal_valid
→ (4) evidence coverage matrix in reports
→ (1) advisory screenshot lane (capped, traced)
→ (3) consistency ambiguity signals (advisory)
→ (2) runtime classification labels (inferred only)
→ (5) sufficiency map in reviewer UI (advisory)
→ pilot observation — no authority upgrades without freeze
```

**Forbidden before pilot behaviour stable:** prompt-only “fixes”, autonomous runtime claims, sufficiency → achieved wiring.

---

## Review questions (per release touching evidence)

1. Did any new path imply `verified` without runtime proof?
2. Is every new analysis type listed in the coverage matrix?
3. Did advisory stay out of achieved logic?
4. Are canonical phrases used in exports (not prompt-only)?
5. Would a teacher see **what was not seen** as clearly as what was?

If any answer is no → treat as governance regression, not a model quality issue.

---

## Next phase: governed runtime evidence chain

After human pilot gate passes, follow [`RUNTIME_EVIDENCE_CHAIN_ROADMAP.md`](RUNTIME_EVIDENCE_CHAIN_ROADMAP.md):

```text
Pilot governance observatory
→ L4 governed sandbox (observation only)
→ runtime telemetry graph
→ runtime-to-criterion mapping (advisory)
→ human-governed runtime review
→ operational governance validation
```

L4 semantics frozen in [`RUNTIME_OBSERVATION_CONTRACT_v1.md`](RUNTIME_OBSERVATION_CONTRACT_v1.md).  
Implementation stub: `app/runtime_observation_contract.py`.

**Forbidden transition:** `runtime observed → criterion achieved`  
**Required chain:** `runtime observed → evidence → authority negotiated → human review → criterion decision`
