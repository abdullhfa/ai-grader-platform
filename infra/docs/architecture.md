# Architecture (Frozen v1.0)

**Status:** FROZEN — changes require major version bump  
**Platform:** 1.0.0-institutional

## Layer isolation

```
┌─────────────┐
│   Security  │  SSO → RBAC → Scan → Rate limit
├─────────────┤
│  Governance │  Examiner → Appeals → Signoff
├─────────────┤
│  Reasoning  │  Evidence graph → Multi-agent → Arbitration
├─────────────┤
│  Gameplay   │  CV → Timeline → Detectors
├─────────────┤
│   Runtime   │  Unity/Web/Godot → Sandbox → Telemetry
└─────────────┘
```

## Truth anchor

```
Replay Snapshot = canonical truth
```

LLM, logs, and screenshots are corroboration only.

## Async pipelines

```
submission → quarantine → malware_jobs → runtime_jobs → gameplay_jobs
           → reasoning_jobs → governance → archive
```

## Contract references

- `schemas/CONTRACT_MANIFEST.json`
- `GET /api/contracts/freeze`
