# Scratch Runtime

- Extensions: `.sb3`, `.sb2` (see `game_engine_signatures.py`)
- BASIC: `scratch_static_graph` — parses project JSON, **no VM**
- PRO: `scratch_pro_runtime_verification` — graph + optional VM
- Static graph alone → `runtime_verified = False`
- Inventory: classified as `executable` + `source` (`artifact_kind: scratch_project`)
