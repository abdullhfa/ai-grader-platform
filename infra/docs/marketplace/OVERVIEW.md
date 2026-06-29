# Market Launch — Platform Overview

## What is replay-backed evaluation?

Student submissions are executed in an isolated runtime sandbox. The platform captures **gameplay observation**, builds an **evidence graph**, and freezes a **replay snapshot** as the canonical truth record.

```
runtime execution → gameplay timeline → evidence graph → replay snapshot → governance
```

The LLM provides reasoning only — it is never the source of truth.

## Why deterministic grading?

- Same submission → same replay hash (integrity heartbeat)
- Appeals review frozen snapshots — no re-execution
- Auditors can verify `deterministic_hash.json` at any time
- Institutional signoff binds to tamper-verified hashes

## Why governance matters?

- Examiner investigation UI (replay-first)
- Override + signoff with audit trail
- Appeals workflow (snapshot-only)
- Incident response: audit freeze → replay preservation

## Supported engines (market launch)

| Engine | Maturity | Runtime path |
|--------|----------|--------------|
| Unity | 90–95% | Full pipeline |
| Godot | 80–85% | Export + smoke |
| Web/HTML5 | 85–90% | Playwright headless |
| GameMaker | 75–80% | EXE/HTML5 + artifact analysis |

## One-command deploy

```bash
docker compose up --build
```

Or staging:

```bash
python tools/deploy_staging.py
```

## Demo samples

See `demos/samples/` for Unity, Godot, GameMaker, and Web stubs.
