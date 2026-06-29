# Hallucination Control

## Risks

- AI claims "تم تحقيق المعيار" when evidence is documentary only
- AI invents Bug Log / Test Plan requirements not in assignment brief
- AI confuses coverage % with achieved status

## Mitigations

- Deterministic rubric merge (`deterministic_engine.py`)
- `enforce_feedback_achieved_consistency`
- Runtime Evidence Gate terminal seal
- `evidence_strength` confidence scoring
- Arabic diagnostics with authority labels
