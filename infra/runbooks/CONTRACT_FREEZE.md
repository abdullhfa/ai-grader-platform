# Contract Freeze Policy

Platform contracts are **frozen** at `schemas/CONTRACT_MANIFEST.json`.

## Official freeze registry

| Element | Version | Schema / reference | Status |
|---------|---------|-------------------|--------|
| Replay format | 1.0 | `replay.schema.json` | **FROZEN** |
| Evidence graph | 1.0 | `evidence.schema.json` | **FROZEN** |
| Governance flow | 1.0 | `infra/docs/governance_flow.md` | **FROZEN** |
| API contracts | 1.0 | `api_contracts_v1.json` | **FROZEN** |
| Audit events | 1.0 | `audit.schema.json` | **FROZEN** |
| Signoff hash | 1.0 | `governance.schema.json` + `tamper_verification` | **FROZEN** |
| Gameplay timeline | 1.0 | `gameplay.schema.json` | **FROZEN** |
| Evidence reasoning | 1.0 | `reasoning.schema.json` | **FROZEN** |

Manifest: `schemas/CONTRACT_MANIFEST.json` (`status: frozen`, `frozen_at: 2026-05-27`).

## Policy: freeze + document + validate

- **Do not** change frozen contracts without a major version bump and migration path.
- **Do** validate via `GET /api/contracts/validate` on every deploy.
- **Do** preserve replay v1 readability indefinitely.

## During controlled rollout

**Stability > Features.** No contract or schema changes during staging, external pentest, or canary. Operational tuning only (scaling, alerts, retention).

## Breaking change policy

- Replay snapshot v1 must remain readable indefinitely.
- Any incompatible change requires a **major version bump** and migration path.
- Validate: `GET /api/contracts/validate`

## Truth anchor

```
Replay Snapshot = canonical truth
```

LLM output, raw logs, and screenshots alone are never authoritative.
