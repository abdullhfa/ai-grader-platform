# Replay Contract (Frozen v1.0)

**Status:** FROZEN  
**Schema:** `schemas/replay.schema.json`  
**Version field:** `replay_schema_version: "1.0"`

## Layout

```
uploads/replay_snapshots/{submission_key}/{session_id}/
  runtime/runtime.json
  gameplay/gameplay.json
  timeline/timeline.json
  evidence/evidence.json
  ai_reasoning/ai_reasoning.json
  grading_summary/grading_summary.json
  screenshots/
  deterministic_hash.json
```

## Manifest (`deterministic_hash.json`)

Required fields (v1.0+):

| Field | Purpose |
|-------|---------|
| `deterministic_hash` | SHA-256 content anchor |
| `replay_schema_version` | Compatibility |
| `reasoning_schema_version` | Reasoning layer version |
| `audit_schema_version` | Audit event version |
| `truth_anchor` | `replay_snapshot_canonical` |

## Compatibility

- v1.0 snapshots readable indefinitely
- Legacy snapshots: auto-stamped via `migrate_replay_manifest()`
- Breaking changes: major version bump only

## Verification

```bash
GET /api/security/tamper/replay/{submission_key}/{session_id}
```

Expected: `integrity: verified`

## Appeals rule

Appeals MUST use frozen replay snapshot — **no runtime re-execution**.
