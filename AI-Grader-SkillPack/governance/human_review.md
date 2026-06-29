# Human Review (L5)

## Triggers

- GameMaker PRO: automated gameplay loop unreliable
- Runtime partial / structure-only analysis
- `achievement_authority = HUMAN_REVIEW_REQUIRED`

## L5 fields

```python
l5_human_playtest.status == "complete_visual"
l5_human_playtest.verified == True
runtime_observation_report.human_playtest_verified == True
```

## Policy

L5 satisfies Runtime Evidence Gate for C.P6/M3/D3.
L4 alone does **not** substitute L5 for GameMaker PRO playtest-gated criteria.

## UI

Human moderation templates: `human_moderation.html`, playtest merge via `submission_playtest.py`.
