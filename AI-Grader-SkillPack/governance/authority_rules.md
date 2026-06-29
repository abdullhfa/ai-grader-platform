# Authority Rules

## Achievement authority values

| Value | Meaning |
|-------|---------|
| `DETERMINISTIC_DOCUMENTARY` | Text/doc evidence path |
| `RUNTIME_OBSERVATION_L4` | Automated sandbox observation |
| `HUMAN_PLAYTEST_L5` | Teacher verified playtest |
| `RUNTIME_GATE_BLOCKED` | Terminal gate demotion |
| `RUNTIME_INSUFFICIENT` | Partial runtime, not awardable |
| `HUMAN_REVIEW_REQUIRED` | Needs L5 before award |

## Evidence ladder (L0–L5)

- L0: no runtime evidence
- L1: executable detected (artifact acknowledgment)
- L2: screenshot candidates (advisory)
- L3: gameplay video (advisory inference)
- L4: runtime observed (partial)
- L5: human verified replay (never auto-assigned)

## Rule

Higher authority cannot be claimed from lower-level evidence alone.
