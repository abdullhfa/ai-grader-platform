# GOVERNANCE_FREEZE_v2 (DRAFT)

**Status:** DRAFT — pending signed epoch verdict (`epoch_transition_justified_institutionally`)  
**Prerequisite:** Governance Epoch Workshop Review on full pilot cohort  
**Supersedes baseline:** [`GOVERNANCE_FREEZE_v1.md`](GOVERNANCE_FREEZE_v1.md) (partial evolution — not full authority expansion)

**Date drafted:** 2026-05-20

---

## Purpose

Evolve **institutional authority semantics** after pilot proves governance stability — not AI correctness.

```text
pilot success proves: institutional governance stability under controlled ambiguity
pilot does NOT prove: correctness · AI intelligence · autonomous grading readiness
```

This freeze authorizes **observational L4 only**. Human authority remains mandatory through L5.

---

## Authority table (v2)

| Element | State |
| ------- | ----- |
| L4 allowed? | **Yes — partial (observational only)** |
| Max runtime authority | observational only |
| Forbidden claims | still forbidden (see v1 + L4 contract) |
| Auto-achieved | **forbidden** |
| Sandbox semantics | observational |
| Human authority | **mandatory** |

---

## What changes from v1

| v1 | v2 |
| -- | -- |
| L4 reserved — no auto-run | Minimal L4 sandbox permitted under contract |
| max auto runtime level = L3 | max auto runtime level = L4 (observation signals only) |
| runtime_observation_sandbox gated off | enabled after signed verdict |
| evidence-governed assessment | runtime-observable educational assessment (advisory layer) |

```text
evidence-governed assessment  →  runtime-observable educational assessment
                                      (observation remains advisory until human review)
```

---

## Minimal L4 sandbox scope (v2 first release)

### Permitted

| Function | Allowed |
| -------- | ------- |
| launch exe/apk (controlled) | yes |
| isolated execution context | yes (timeout-bound; VM when available) |
| timeout | yes |
| screenshot capture | yes (when host supports) |
| crash detection | yes |
| telemetry logging | yes |

### Forbidden

| Function | Allowed |
| -------- | ------- |
| autonomous grading | **no** |
| gameplay narration | **no** |
| criterion achievement | **no** |
| AI evaluation of runtime | **no** |
| `runtime observed → achieved` wire | **no** |

---

## Runtime telemetry graph (v2)

Required event types (advisory timeline — not grading input):

```text
process_started
scene_loaded
input_detected
score_changed
collision_detected
level_transition
runtime_duration
crash_state
```

Module: `app/runtime_telemetry_graph.py`

---

## Runtime replay (v2)

Human reviewer must see:

- runtime screenshots
- telemetry timeline
- crashes
- runtime state
- contradictions
- authority level

**Rule:** runtime observation remains advisory until human review (L5).

---

## Activation gate

v2 becomes **active** only when ALL are true:

1. [ ] Governance Epoch Workshop Review completed (`/governance-epoch-workshop`)
2. [ ] Signed institutional artifact with verdict `epoch_transition_justified_institutionally`
3. [ ] RFC package + mitigation lineage attached to artifact chain
4. [ ] No unresolved S5 in pilot cohort

Until then: `GOVERNANCE_FREEZE_v1` remains active; L4 sandbox is **gated**.

API: `/api/governance/l4-decision/package`

---

## Machine-readable snapshot

See [`GOVERNANCE_FREEZE_v2.json`](GOVERNANCE_FREEZE_v2.json).

---

## Confidence acceleration warning

```text
confidence acceleration = pilot success → "system ready for full autonomous grading"
```

This is **explicitly forbidden**. v2 enables observation infrastructure — not grading autonomy.
