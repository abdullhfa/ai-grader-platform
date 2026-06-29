# Phase 3 — Institutional Evidence Calibration v1

**Status:** DESIGN FRAMEWORK COMPLETE — **without automatic scoring**  
**Design completed:** 2026-05-24 (Path B — Phase 2 gap waived for design only)  
**Operationalization:** blocked until Phase 2 + epoch deliberation sign-off  
**Not:** runtime expansion · L4 sandbox · telemetry authority · hidden probabilistic authority automation

---

## Constitutional principle

```text
confidence is not authority
```

Even when evidence is strong · runtime observed · telemetry present · corroboration high:

```text
criterion authority remains institutionally mediated
```

Not mathematically emergent.

---

## Phase transition

| Phase 2 question | Phase 3 question |
|------------------|------------------|
| can humans preserve restraint under observability pressure? | what kinds of evidence legitimately deserve institutional confidence? |
| epistemic behaviour | evidence sufficiency |
| observe only | deliberate + calibrate |

Traditional AI tries to **predict correctness**.  
This project builds an **institutional confidence ecology**:

- how evidence interacts,
- how plausibility accumulates,
- how contradictions weaken authority,
- how sufficiency is built,
- how uncertainty stays visible despite rising confidence.

---

## Build order (Phase 3 internal sequence)

| Step | Artifact | Design status |
|------|----------|---------------|
| 1 | [Evidence Sufficiency Atlas](EVIDENCE_SUFFICIENCY_ATLAS_v1.md) | **complete** (5 batch entries + generic exemplars) |
| 2 | [Institutional Confidence Bands](INSTITUTIONAL_CONFIDENCE_BANDS_v1.md) | **complete** |
| 3 | [Sufficiency Contours](SUFFICIENCY_CONTOURS_v1.md) | **complete** (triad B4/B8) |
| 4 | [Confidence Language Registry](CONFIDENCE_LANGUAGE_REGISTRY_v1.md) | **complete** |
| 5 | [Contradiction Modulation](CONTRADICTION_MODULATION_v1.md) | **complete** |
| 6 | Sufficiency Deliberation Workshops | **pending** (live facilitator sessions) |
| 7 | Replay as Deliberation Surface | **pending** (read-only UI — gated) |

**Only after Phase 3 design + Phase 2 complete:** discuss bounded L4 runtime observation inside calibrated ecology.

**Do not operationalize too early.** Atlas · bands · modulation remain deliberative constitutional guidance — not hidden inference machinery.

---

## 1. Evidence Sufficiency Atlas

**Not** numeric weights alone.

```text
institutional sufficiency exemplars
```

| Case | Why considered sufficient (or not) | Typical band |
|------|-------------------------------------|--------------|
| code + coherent gameplay screenshots | implementation plausibility | bounded → strong |
| structured testing logs + documented fixes | operational maturity | strong |
| video only | insufficient alone — modality dominance risk | weak |
| exe only | acknowledgement only — not gameplay | weak |
| replay + unresolved contradictions | bounded confidence only — HOLD | bounded (capped) |
| Godot source + L2 folder screenshots + no video | bounded implementation case (Ahmed-type) | bounded |
| telemetry + no testing narrative | observation without maturity | observed, not sufficient |
| contradiction-free multi-artifact chain | strengthens trust — never auto-elevates | modulates upward |

**Ahmed anchor:** reveals where U is pedagogically harsh, D was inflated, and where **bounded sufficient implementation plausibility** lives — calibration target, not automation target.

Atlas entries are **workshop-authored exemplars** — reference for deliberation, not grading inputs.

---

## 2. Institutional Confidence Bands

See dedicated specification: [`INSTITUTIONAL_CONFIDENCE_BANDS_v1.md`](INSTITUTIONAL_CONFIDENCE_BANDS_v1.md)

Deliberative labels — not grades · not auto-criterion achievement:

| Band | Meaning |
|------|---------|
| `weak_plausibility` | signals only — insufficient alone |
| `bounded_plausibility` | pedagogically acceptable mix |
| `strong_implementation_confidence` | coherent multi-artifact case |
| `operationally_observed` | runtime observed — **not** verified |
| `human_confirmed` | final institutional authority |

Bands describe **confidence ecology position** — they do not trigger achievement.

**Guard against semantic creep:** `strong_implementation_confidence` must never be read as «almost achieved». See separation table in [Atlas](EVIDENCE_SUFFICIENCY_ATLAS_v1.md).

---

## 3. Confidence Language Registry

See companion: [`CONFIDENCE_LANGUAGE_REGISTRY_v1.md`](CONFIDENCE_LANGUAGE_REGISTRY_v1.md)

Language becomes more dangerous in Phase 3 than in Phase 2.

```text
confidence semantics explicitly governed
```

| Phrase | Semantic effect | Authority risk |
|--------|-----------------|----------------|
| suggests implementation | bounded | low |
| strongly supports implementation | higher confidence | medium |
| operationally observed | runtime layer | medium-high |
| confirms criterion | authority escalation | **forbidden without human verdict** |
| verified / game works | implicit legitimacy | **leakage** |

Phase 2 lexicon guarded *behaviour under observability*.  
Phase 3 lexicon guards *confidence → authority drift*.

---

## 4. Contradiction Modulation Logic

See dedicated specification: [`CONTRADICTION_MODULATION_v1.md`](CONTRADICTION_MODULATION_v1.md)

Not all contradictions are equal. They **modulate confidence** — they do not silently collapse it.

| Contradiction type | Modulation effect |
|--------------------|-------------------|
| video ≠ screenshots | moderate downgrade |
| code genre ≠ claimed gameplay | strong downgrade |
| runtime hints ≠ stated mechanics | strong downgrade |
| missing testing logs | bounded caution |
| asset screenshots in L2 folder | modality / folder boundary (Ahmed) |

```text
contradictions should modulate confidence
not silently collapse it
```

Contradictions remain **visible** in replay and deliberation — ambiguity persistence is constitutional.

---

## 5. Evidence Interaction Logic (reference)

Workshop-calibrated advisory — not silent rules:

| Combination | Institutional effect |
|-------------|---------------------|
| code + screenshots | strengthens plausibility |
| video + contradictions | lowers authority — HOLD |
| telemetry + no testing | observation without maturity |
| strong testing + coherent runtime | confidence rises — still bounded |
| exe only + no corroboration | weak — ambiguity preserved |

---

## 6. Sufficiency Deliberation Workshops

Different from Phase 2.

| Phase 2 | Phase 3 |
|---------|---------|
| did restraint survive? | what combinations feel institutionally sufficient and why? |
| semantic leakage | evidence sufficiency |
| observe only | deliberate + document exemplars |

Per criterion cluster:

```text
what evidence combinations legitimately justify criterion confidence?
```

Outputs feed the **Atlas** — not the grader.

---

## 7. Replay as Deliberation Surface

| Today (Phase 1–2) | Phase 3 |
|-------------------|---------|
| provenance replay | institutional evidence reasoning workspace |

Displays (all advisory):

- evidence strengths,
- contradictions + modulation notes,
- corroboration chains,
- confidence band candidates,
- ambiguity persistence,
- human verdict slot (required for any authority elevation).

---

## Critical constraint — Phase 3 failure mode

```text
weights quietly becoming automated authority
```

Forbidden:

- hidden score / weight sum,
- confidence accumulation → auto-achieve,
- silent escalation,
- emergent grading,
- bands → grade level without sign-off.

```text
design only — without automatic scoring
```

Keeps **human institutional deliberation** at the centre.

---

## Sequence (full)

```text
Phase 2: workshop → synthesis → cooling → ritual reading → semantic memory
    ↓
Phase 3: Atlas → Bands → Language → Contradiction modulation → Workshops → Replay deliberation
    ↓
Then discuss: bounded L4 runtime observation inside calibrated confidence ecology
```

Runtime enters as **calibrated institutional confidence ecology** — not psychologically dominant evidence.

---

## Implementation files (design complete — runtime gated)

| Artifact | Role | Runtime |
|----------|------|---------|
| `EVIDENCE_SUFFICIENCY_ATLAS_v1.md` | **primary** — constitutional sufficiency memory | design only |
| `INSTITUTIONAL_CONFIDENCE_BANDS_v1.md` | band vocabulary | design only |
| `SUFFICIENCY_CONTOURS_v1.md` | contour triad | design only |
| `CONTRADICTION_MODULATION_v1.md` | modulation taxonomy | design only |
| `CONFIDENCE_LANGUAGE_REGISTRY_v1.md` | governed confidence semantics | design only |
| `EVIDENCE_WEIGHT_CALIBRATION_v1.md` | master Phase 3 design (this file) | design only |
| `confidence_band_vocabulary.py` | **not created** — markdown design only until epoch sign-off | blocked |
| `contradiction_modulation_reference.py` | **not created** — markdown design only until epoch sign-off | blocked |

**Gate:** Phase 2 exit + epoch deliberation sign-off before any artifact affects grading paths.
