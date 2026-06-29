# Governance Flow (Frozen v1.0)

**Status:** FROZEN  
**Schema:** `schemas/governance.schema.json`

## Workflow

```
AI Evaluation → FinalDecision → Examiner Review → Appeal → Sign-off
                                      ↑
                              ReplayInspectionBundle
```

## States

| Stage | Actor | Output |
|-------|-------|--------|
| Auto grading | System | `ai_reasoning` + replay snapshot |
| Examiner review | Examiner | Investigation UI |
| Override | Examiner | Immutable audit event |
| Escalation | Examiner | Senior examiner queue |
| Sign-off | Senior Examiner | `signed_evaluation_hash` |
| Appeal | Student | Replay-backed case |
| Resolution | Senior Examiner | Appeal decision record |

## RBAC

| Role | Permissions |
|------|-------------|
| student | view feedback, submit appeal |
| examiner | override, escalate, view replay |
| senior_examiner | signoff, resolve appeals |
| admin | audit export, policy admin |

## Audit

- Governance: `uploads/governance/audit/{session}/audit_log.jsonl`
- Security: `uploads/security/security_audit.jsonl`
- Identity: `identity_audit_logs` (DB)

## UI

- `/governance/examiner` — investigation interface (replay-first)
