# Institutional Confidence Bands v1

**Status:** DESIGN ONLY — deliberative constitutional vocabulary  
**Purpose:** name **confidence ecology positions** — not grades · not criterion achievement  
**Not:** weights · hidden scoring · probabilistic authority · band→grade mapping

---

## Core question (Phase 3)

```text
what kind of confidence is institutionally legitimate?
```

**Not:** `what score should AI give?`

---

## Principle

```text
confidence is not authority
```

Bands describe **how much institutional confidence** a evidence mix may **legitimately carry** in deliberation — they never trigger achievement or scoring.

---

## Standard bands (evidence ecology)

| Band ID | Label (EN) | Meaning | Authority ceiling |
|---------|------------|---------|-------------------|
| `weak_plausibility` | Weak plausibility | signals only — modality or artifact alone | insufficient alone · HOLD |
| `bounded_plausibility` | Bounded plausibility | pedagogically acceptable mix — corroboration expected | advisory · no auto-achieve |
| `strong_implementation_confidence` | Strong implementation confidence | coherent multi-artifact case | still not verified |
| `operationally_observed` | Operationally observed | runtime layer reached (L4 contract) | observation ≠ criterion |
| `human_confirmed` | Human confirmed | final institutional authority | verdict channel only |

**Guard:** `strong_implementation_confidence` ≠ «almost achieved».

---

## Contour-specific bands (constitutional — not grades)

These bands name **deformation pathways** under partial observability — see [`SUFFICIENCY_CONTOURS_v1.md`](SUFFICIENCY_CONTOURS_v1.md).

| Band ID | Contour | Meaning |
|---------|---------|---------|
| `representational_capture_under_noisy_implementation_ecology` | B4-001 surface capture | judgment stabilized on metabolizable surface — not richest ecology |
| `pedagogical_sufficiency_contour_ambiguity_under_unequal_implementation_density` | B8-002 inflation | legibility/density asymmetry — confidence inflates on chosen surface |
| `failure_confidence_stabilization_under_degraded_interpretive_legibility` | B8-003 closure | failure stabilizes before interpretive coherence |

Contour bands are **constitutional memory labels** — not classifier outputs.

---

## Typical band ladder (workshop use)

```text
weak_plausibility
    ↓  (+ corroboration, − contradictions)
bounded_plausibility
    ↓  (+ multi-artifact chain, + process signals)
strong_implementation_confidence
    ↓  (+ governed runtime observation — L4 when permitted)
operationally_observed
    ↓  (human institutional verdict only)
human_confirmed
```

**No automatic transitions.** Facilitators assign bands in deliberation — not algorithms.

---

## Mapping to Atlas entries (reference)

| Atlas | Typical band |
|-------|----------------|
| ATLAS-001 (code + screenshots) | `bounded_plausibility` → may modulate toward `strong_implementation_confidence` |
| ATLAS-003 (video only) | `weak_plausibility` |
| ATLAS-004 (exe only) | `weak_plausibility` |
| ATLAS-B8-001 (Godot cluster) | `bounded_plausibility` |
| ATLAS-B8-002 | contour band (inflation) |
| ATLAS-B8-003 | contour band (closure) |
| ATLAS-B4-001 | contour band (surface capture) |

---

## Forbidden uses

Until epoch sign-off + explicit governance adoption:

- ❌ inject bands into `batch_grader` prompts as weights  
- ❌ band → percentage mapping  
- ❌ band → grade level (U/P/M/D)  
- ❌ confidence accumulation arithmetic  
- ❌ probabilistic «confidence score»  

Default:

```text
deliberative constitutional guidance only
```

---

## Relation to other artifacts

| Document | Role |
|----------|------|
| [`EVIDENCE_SUFFICIENCY_ATLAS_v1.md`](EVIDENCE_SUFFICIENCY_ATLAS_v1.md) | exemplars that illustrate bands |
| [`SUFFICIENCY_CONTOURS_v1.md`](SUFFICIENCY_CONTOURS_v1.md) | contour bands |
| [`CONTRADICTION_MODULATION_v1.md`](CONTRADICTION_MODULATION_v1.md) | how bands shift downward |
| [`CONFIDENCE_LANGUAGE_REGISTRY_v1.md`](CONFIDENCE_LANGUAGE_REGISTRY_v1.md) | phrases permitted per band tier |
