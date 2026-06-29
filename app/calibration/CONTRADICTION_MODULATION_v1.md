# Contradiction Modulation v1

**Status:** DESIGN ONLY — advisory reference for deliberation and replay  
**Purpose:** contradictions **modulate** confidence contours — they do **not** erase evidence  
**Not:** automatic downgrade rules · hidden scoring · probabilistic collapse

---

## Principle

```text
contradictions reshape confidence contours
not: contradiction exists → evidence invalid
```

Ambiguity persistence is **constitutional** — contradictions remain visible in replay.

---

## Modulation strength taxonomy

| Level | Label | Effect on confidence band | Eliminates evidence? |
|-------|-------|---------------------------|----------------------|
| **L0** | `none` | no change | — |
| **L1** | `bounded_caution` | hold at current band · cap upward movement | no |
| **L2** | `moderate_downward` | shift one step down ecology ladder | no |
| **L3** | `strong_downward` | shift two steps or cap at `weak_plausibility` | no |
| **L4** | `hold_pending_human` | freeze band movement until facilitator verdict | no |

**No L5 «eliminate».** Evidence remains in ecology — only confidence modulates.

---

## Contradiction types (reference matrix)

| Type | Example | Typical modulation | Atlas refs |
|------|---------|-------------------|------------|
| `video_screenshot_mismatch` | video shows different UI than screenshots | L2 moderate | ATLAS-003 · 005 |
| `code_genre_gameplay_mismatch` | code genre ≠ claimed gameplay mechanics | L3 strong | ATLAS-005 |
| `runtime_hint_mechanics_mismatch` | telemetry/hints ≠ stated mechanics | L3 strong | ATLAS-007 |
| `missing_testing_narrative` | implementation without process signal | L1 bounded caution | ATLAS-002 · B8-001 |
| `l2_folder_boundary_violation` | asset PNGs counted as gameplay evidence | L2 moderate | ATLAS-006 · Ahmed |
| `exe_readme_contradiction` | exe present · README describes different game | L2 moderate | ATLAS-004 |
| `doc_implementation_contradiction` | doc claims features absent in code surface | L2–L3 | B8-002 |
| `surface_ecology_substitution` | graded doc ≠ implementation archive | L3 + contour B4-001 | ATLAS-B4-001 · B8-003 |
| `identity_label_weakness` | folder name ≠ verified student identity | L1 on identity only — not code | ATLAS-B8-004 |
| `multi_build_name_drift` | conflicting build names in archive | L1–L2 · ambiguity preserved | batch 4 (حسين) |

---

## Interaction with confidence bands

Starting band from evidence mix (workshop-assigned):

```text
bounded_plausibility
    + unresolved L2 contradiction  →  remains bounded or shifts toward weak
    + L3 contradiction             →  weak_plausibility or HOLD (L4)
    + contradiction resolved in replay → may modulate upward (facilitator only)
```

**Never:** contradiction → auto U · auto grade change · silent prompt injection.

---

## Interaction with contours

| Contour | Contradiction role |
|---------|-------------------|
| **B4-001** | substitution itself is a structural «contradiction» between ecology and graded surface — modulate trust in **intake completeness** not student intent |
| **B8-002** | contradictions may **reduce** inflation pressure — legibility alone must not override |
| **B8-003** | premature closure may **ignore** contradictions that would reopen interpretive space |

---

## Replay deliberation display (future — read-only)

When epoch approves read-only surfacing, replay may show:

- contradiction type tags (advisory),
- suggested modulation level (facilitator override required),
- **ambiguity persistence** flag,
- human verdict slot.

Until gate: markdown reference only.

---

## Workshop procedure

1. List contradictions visible in artifact chain  
2. Classify type (matrix above)  
3. Assign modulation level (L0–L4)  
4. Record in atlas entry `modulation` field  
5. Select registry phrases (Layer 1–2 only unless verdict)  

---

## Forbidden

- ❌ `contradiction_modulation_reference.py` auto-applied to grader (not created — design markdown only)  
- ❌ numeric penalty weights  
- ❌ contradiction count → score formula  
- ❌ silent collapse to zero evidence  

```text
design only — without automatic scoring
operationalization: blocked
```

---

## Relation to other artifacts

| Document | Role |
|----------|------|
| [`INSTITUTIONAL_CONFIDENCE_BANDS_v1.md`](INSTITUTIONAL_CONFIDENCE_BANDS_v1.md) | bands that modulation moves between |
| [`SUFFICIENCY_CONTOURS_v1.md`](SUFFICIENCY_CONTOURS_v1.md) | contour-aware modulation |
| [`EVIDENCE_SUFFICIENCY_ATLAS_v1.md`](EVIDENCE_SUFFICIENCY_ATLAS_v1.md) | per-case modulation notes |
| [`CONFIDENCE_LANGUAGE_REGISTRY_v1.md`](CONFIDENCE_LANGUAGE_REGISTRY_v1.md) | phrasing after modulation |
