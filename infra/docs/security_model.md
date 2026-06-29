# Security Model (v1.0)

**Status:** READY — review after external pentest

## Pipeline

```
SSO/OIDC → RBAC (DB) → Malware Scan → Quarantine → Sandbox → Runtime
    → Evidence → Governance → Tamper Verification → Archive
```

## Secrets

Precedence: Vault → Kubernetes Secrets → env  
Policy: `app/security/secret_policy.py`

## Scanning

| Layer | Tool |
|-------|------|
| Hash reputation | SHA256 blocklist |
| Heuristic | YARA-style patterns |
| AV | ClamAV (optional sidecar) |
| Async | `malware_jobs` queue |

## Tamper detection

```
tamper_verification_hash = SHA256(artifact_type + content + replay_hash)
```

## Rate limiting

Redis-backed on: appeals, exports, runtime, override, signoff

## Incident response

```
security_event → audit freeze → replay preservation → investigation → resolution
```

API: `POST /api/ops/incidents`

## Container hardening

- Non-root sandbox user
- seccomp profile
- Network isolation (`--network none`)
- Read-only FS + tmpfs

## Pending (post-pentest)

- Full AppArmor profiles per worker
- WORM object storage / legal hold
- Enterprise SAML

## Pentest

See `infra/runbooks/PENTEST_CHECKLIST.md`
