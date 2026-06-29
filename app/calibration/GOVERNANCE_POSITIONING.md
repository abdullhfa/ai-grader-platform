# Governance positioning (BTEC AI Grader)

## What this system is

**Decision-support governance system** — not an autonomous AI grading platform.

Success is measured by:

```text
stability of institutional trust under uncertainty
```

not:

```text
better model outputs alone
```

## Core idea

```text
uncertainty itself is governed
```

```text
ingestion semantics ≠ grading authority
```

Claim-boundary detail, authority tiers, and engineering priorities: [`EVIDENCE_GOVERNANCE_ROADMAP.md`](EVIDENCE_GOVERNANCE_ROADMAP.md).

**Frozen baseline (pre-sandbox):** [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md)

Assessment **legitimacy** — not only assessment automation.

## Phase (current)

```text
The system is no longer in feature maturation phase.
It is entering institutionally constrained reliability observation
under human-governed assessment conditions.
```

```text
The next milestone is not higher capability,
but credible behaviour under real educational disagreement.
```

This is **socio-technical governance validation** — not ordinary software QA.

## Intentional constraint

| Old reading | Accurate reading |
| ----------- | ---------------- |
| system not finished | system **intentionally constrained** pending institutional evidence |
| missing calibration | calibration **architecture exists**; **live human-labelled cohort** pending |
| workshop empty = blocked | `workshop_incomplete` = **no governance signal yet** (not HOLD) |

## Trust-preserving rollout

Build governance **before** large cohorts:

- freeze windows, calibration_diff, taxonomy
- shadow sufficiency (observation only — does not set `achieved`)
- human review gates (advisory)
- stress cohorts, workshop, actionable cluster thresholds
- HOLD discipline, single-intent Run3 only when justified

**Not wired:** shadow → achieved. **Not claiming:** production-ready from synthetic/stress alone.

## What is actually missing

```text
human-labelled institutional cohorts
```

Real **disagreement ecology**: borderline evidence, inconsistent assessor judgment, partial sufficiency, conflicting interpretations.

Pilot (20–30) = **observed trust formation cycle** — not capability proof.

## Operational sequence (now)

1. Complete `reliability_review_workshop_v1.json`
2. `aggregate_workshop_friction` → `workshop_synthesis_v1.json`
3. Require `governance_signal_valid: true`
4. Then only: **HOLD** | **smallest justified Run3** | pause if multiple clusters
5. Then: real pilot under `freeze_real_pilot_v1` — observe, do not fix quickly
6. Move rarely; prefer **No change recommended this cycle**

## Production / security (later)

Internet hardening, Docker, full test suites, autonomous final grades — **deferred** until institutional behaviour is credible under real conditions.

## Trust target (not 100% autonomous certainty)

Goal is **not** `perfect grading certainty` or `100% autonomous trust`.

Goal:

```text
predictable, governable, trustworthy behaviour under institutional disagreement
```

Errors must be: **visible**, **containable**, **non-destructive to trust**, **subject to human review**.

Raising AI authority for technical accuracy often **erodes** the governance that built trust (fewer HOLDs, weaker gates, overconfidence semantics).

## Institutional evidence layers (roadmap — not feature sprint)

| Layer | Purpose |
| ----- | ------- |
| Human-labelled cohorts | Map **disagreement topology** (20–30 → 100–300); not “train AI” |
| Pilot as governance observatory | Override rates, fatigue, ignored HOLD, insufficiency patterns — **how humans behave with AI in the loop** |
| Reliability / disagreement taxonomy | Formalise ambiguity, evidence absence, rubric drift, assessor variance, weak corroboration |
| Authority boundaries (fixed) | AI assists institutional judgement; **never replaces it** — even at high accuracy |
| Governance metrics > accuracy alone | HOLD appropriateness, override frequency, unresolved disagreement, sufficiency confidence, trust retention, calibration stability |
| Longitudinal drift | Freeze + diff + snapshots as **cadence**, not only during dev |
| Verifier workflows (later) | Heatmaps, risky assessments, low corroboration, overrides, assessor divergence |
| No AI expansion before behaviour stable | Multimodal/agents/autonomous grading **after** `stable institutional behaviour` |

**Trusted enough** when:

```text
disagreement is predictable, containable, auditable, institutionally survivable
```

not when `accuracy = 95%` alone.

## Institutional expansion map (1–2 years)

**Wrong expansion:** `more AI features → system better`  
**Right expansion:** institution more observable, reviewable, governable, resilient under disagreement.

| Phase | Focus | Not |
| ----- | ----- | --- |
| **1 — Now** | Governance core: workshop, probe, taxonomy, HOLD, pilot, freeze, overrides, corroboration | Feature sprawl |
| **2** | Observation layer: reviewer analytics, calibration timeline, disagreement heatmaps, governance replay | Accuracy dashboards only |
| **3** | Evidence governance intelligence: graphs, sufficiency engine, authenticity signals (**advisory only**) — see [`EVIDENCE_GOVERNANCE_ROADMAP.md`](EVIDENCE_GOVERNANCE_ROADMAP.md) | Autonomous grading |
| **4** | Workflow: verifier portal, assessor governance profiles, moderation queues | AI tricks |
| **5** | Longitudinal: cross-cohort stability, unit reliability, trust metrics | “93% accuracy” KPI |
| **6 — Far** | Multi-school: federated calibration, shared taxonomy, external verification / accreditation reports | Premature scale |

**First product expansion after real pilot (not before):** Governance Review Dashboard — HOLD rates, override heatmaps, disagreement categories, corroboration failures, assessor drift, sufficiency confidence, governance anomalies.

Target category:

```text
educational governance infrastructure for evidence-based institutional assessment
```

not `AI grading app`.

## Ordered path from now

```text
workshop complete
→ governance_signal_valid
→ HOLD or smallest Run3
→ pilot 20–30 (observation, not pass/fail)
→ disagreement mapping
→ governance synthesis
→ restrained cohort expansion
→ verifier workflows
→ longitudinal drift monitoring
→ institutional hardening
→ production deployment
```

**Now:** workshop incomplete — no engineering until operational signal.

## Governance rehearsal cohort (synthetic, disagreement-oriented)

Not perfect datasets — **messy educational reality simulation** for governance stress (25 cases, 5 layers):

```powershell
python -m app.calibration.generate_disagreement_cohort --write-tree
```

Outputs: `gold_dataset/unity_gold_disagreement_rehearsal_v1.json`, `synthetic_cohorts/*/case_metadata.json`.

Layers: `clear_pass_cases`, `partial_sufficiency`, `false_confidence`, `disagreement_cases`, `hold_expected`.

Evaluate: uncertainty visible, HOLD when expected, corroboration pressure, advisory stays advisory — **not** «هل AI صح؟» alone.

**Priority:** `workshop` (real reviewer signal) **>** `rehearsal` (synthetic stress). Rehearsal ≠ institutional validation.

### After workshop — one Governance Probe only (not optimization loop)

Run **once** after `governance_signal_valid` + optional HOLD/Run3 — **not** before workshop completes.

```powershell
python -m app.calibration.run_large_scale_calibration `
  --gold app/calibration/gold_dataset/unity_gold_disagreement_rehearsal_v1.json `
  --systems app/calibration/gold_dataset/system_snapshots_disagreement_rehearsal_v1.json `
  --out app/calibration/reports/cal_governance_probe_v1.json `
  --freeze-window freeze_governance_probe_v1
```

Collective review questions (not «did the model score well?»):

- Did governance semantics stay coherent under stress?
- HOLD where expected? corroboration failures clear?
- Advisory stayed advisory? explanation language disciplined?
- Uncertainty visible? borderline cases contained?

**Forbidden after probe:** tuning frenzy, prompt surgery, rubric rewrites, threshold bundles, feature adds. `observe first, optimize later`. Then **real pilot 20–30**.

## Audit report alignment

External audits may read “missing maturity.” Update framing to:

```text
system entering controlled reliability validation phase
```

Keep valid: assistant-only use, mandatory human review, security/deployment gaps for public production.
