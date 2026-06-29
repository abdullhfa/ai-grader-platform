# Refactoring Prompt

Safe refactors:

- Consolidate engine signatures into `game_engine_signatures.py`
- Move promotion logic out of finalizer into governance (preferred long-term)
- Unify grade display to always call `build_grade_display_metrics`

Unsafe without tests:

- Changing `determine_grade_level` band thresholds
- Removing `runtime_gate_block` checks
