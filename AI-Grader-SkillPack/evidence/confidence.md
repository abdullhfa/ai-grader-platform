# Evidence Confidence

## Layers

| Module | Output |
|--------|--------|
| `evidence_strength.py` | `decision_confidence` 0..1 |
| `ai/reliability_layer.py` | AI disagreement risk |
| `evidence_completeness_gate.py` | `has_gaps`, demotion hints |

## Weak source demotion

`weak_src` when extraction coverage < 50% — does **not** apply to Scratch projects (`.sb3` is self-contained source).

## Diagnostic confidence

Arabic diagnostics in `academic_explainability.py` separate:
- file **detected** vs **verified**
- advisory vs institutional authority
