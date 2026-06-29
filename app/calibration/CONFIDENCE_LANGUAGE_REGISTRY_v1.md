# Confidence Language Registry v1

**Status:** DESIGN ONLY — Phase 3 companion to [`EVIDENCE_WEIGHT_CALIBRATION_v1.md`](EVIDENCE_WEIGHT_CALIBRATION_v1.md)  
**Purpose:** govern confidence semantics — prevent confidence → authority drift  
**Not:** automated scoring · prompt injection weights · silent grade influence

---

## Principle

```text
confidence is not authority
```

Every phrase below is **deliberative vocabulary** for workshops, replay, and facilitator reports — not grader instructions.

---

## Layer 1 — Bounded plausibility language

| Phrase (EN) | Phrase (AR) | Permitted context | Authority ceiling |
|-------------|-------------|-------------------|-------------------|
| suggests implementation | يشير إلى تنفيذ | multi-artifact review | advisory only |
| consistent with claimed scope | متسق مع النطاق المclaimed | atlas exemplar discussion | L2–L3 corroborative |
| bounded plausibility | plausibility محدود | sufficiency workshop | no criterion achieve |
| insufficient alone | غير كافٍ وحده | exe-only · video-only cases | HOLD |

---

## Layer 2 — Elevated confidence language

| Phrase | Semantic effect | Requires |
|--------|-----------------|----------|
| strongly supports implementation | higher institutional confidence | atlas exemplar + no unresolved contradiction |
| coherent evidence chain | trust modulation upward | visible corroboration chain in replay |
| operational maturity indicated | process + testing signal | testing logs / structured narrative |
| operationally observed | runtime layer reached | L4 observational contract — not verified |

**Forbidden without human verdict:** confirms criterion · verified achieved · game proven.

---

## Layer 3 — Authority escalation (restricted)

| Phrase | Risk | Status |
|--------|------|--------|
| confirms criterion | direct authority transfer | **human verdict only** |
| criterion achieved (from observation) | leakage | **forbidden** |
| verified / game works / واضح أنها شغالة | implicit legitimacy | Phase 2 leakage — still forbidden |
| therefore Pass / therefore Distinction | grade inference from evidence | **forbidden in system output** |

---

## Confidence vs authority matrix

| Dimension | Confidence | Authority |
|-----------|------------|-----------|
| Source | evidence ecology | institutional verdict |
| Accumulation | plausibility bands | discrete human sign-off |
| Contradictions | modulate downward | may block elevation |
| Runtime | operationally observed | never auto-criterion |
| Language | governed registry | separate verdict channel |

---

## Workshop use

Facilitators label deliberation notes using registry tiers:

1. Which band applies? (`weak` → `bounded` → `strong` → `observed`)
2. Which phrases accurately describe — without escalation?
3. Does any phrase cross into Layer 3 without verdict?

Outputs update **Sufficiency Atlas** — not grading prompts.

---

## Relation to Phase 2 epistemic lexicon

| Phase 2 (`epistemic_leakage_lexicon`) | Phase 3 (this registry) |
|---------------------------------------|-------------------------|
| behaviour under observability | confidence under evidence mix |
| «game verified» leakage | «confirms criterion» leakage |
| facilitator language samples | sufficiency deliberation language |

Both remain **reference only** — no automated gate.

---

## Ahmed calibration language exercise (draft)

For Ahmed-type case, permitted deliberation:

- «Godot source + L2 screenshots **suggest** bounded implementation plausibility for some criteria»
- «exe presence **insufficient alone** for runtime criteria»
- «contradictory artifact signals **modulate confidence downward** for C.P5–C.P7 cluster»

Not permitted without workshop verdict:

- «screenshots **confirm** gameplay criteria»
- «project **verified** therefore Distinction»

---

## Constitutional restraint language (Phase 3 · protected)

These phrases are **institutional memory** — not prompts · not heuristics · not classifier seeds.

| Phrase (EN) | Use |
|-------------|-----|
| the institution may assess what became representationally stable rather than what was evidentially most complete | B4-001 surface capture |
| the institution may assess the archive it could metabolize, not necessarily the archive that existed | intake vs ecology |
| certainty stabilizes around representational cleanliness rather than implementation ecology | metabolization pressure |
| institutional certainty is partly shaped by which surface becomes metabolically central | B4-001 |
| failure confidence ≠ adequate interpretive encounter | B8-003 restraint |
| confidence stabilization is partly shaped by evidence legibility — not only evidence volume | B8-002 |
| contradictions reshape confidence contours — not eliminate evidence | modulation principle |

---

## Contour-linked language (Layer 1–2 only in deliberation)

| Contour | Permitted (Layer 1–2) | Forbidden (Layer 3 without verdict) |
|---------|-------------------------|-------------------------------------|
| B4-001 surface capture | «graded surface suggests bounded narrative plausibility» · «ecology not fully metabolized» | «full project reviewed» · «implementation verified» |
| B8-002 inflation | «legibility may stabilize confidence disproportionately» · «density vs clarity asymmetry» | «clearer presentation proves stronger implementation» |
| B8-003 closure | «failure confidence may stabilize before interpretive coherence» · «intake legibility collapse» | «U proves no implementation» · «insufficient = no ecology» |

---

## Gate

No registry entry may be injected into `batch_grader` prompt as scoring weight until:

- Phase 2 complete,
- Sufficiency Atlas workshop-signed,
- epoch deliberation records explicit language governance adoption.
