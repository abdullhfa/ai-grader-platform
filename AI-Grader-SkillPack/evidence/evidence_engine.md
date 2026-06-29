# Evidence Engine

## Pipeline

1. **Preflight** (`preflight_evidence_scan.py`) — fast filename/path scan
2. **Artifact inventory** (`artifact_inventory.py`) — full file catalog
3. **Evidence completeness gate** (`evidence_completeness_gate.py`) — per-criterion assets
4. **Evidence strength** (`evidence_strength.py`) — confidence 0..1
5. **Coverage score** (`evidence_coverage_score.py`) — weighted % per criterion

## Golden rule

Coverage % = potential evidence in files — **does not mean criterion achieved**.
UI must show disclaimer: refer to «معايير BTEC — تحقق / منح» for institutional decision.
