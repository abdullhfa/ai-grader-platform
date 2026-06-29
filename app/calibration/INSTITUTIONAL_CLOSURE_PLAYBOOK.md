# Institutional Closure Playbook — 8 Phases

> **Engineering: CLOSED** | **Institutional: IN PROGRESS**

---

## Phase 1 — Human Labels Completion

**File:** `app/calibration/human_labels_v1.json`

**Order:**
1. Abdullah (#1)
2. Top 5: #22, #15, #19, #14, #16
3. Bottom 5: #20, #21, #17, #18, #25
4. Remaining → 20+ projects

**Track progress:**
```powershell
.venv\Scripts\python.exe tools\check_human_labels_progress.py
```

**Do NOT:** fabricate `Achieved` / `Not Achieved` — teacher only.

---

## Phase 2 — Pilot Moderation

**Worksheet:** `app/calibration/reports/closure/PILOT_MODERATION_WORKSHEET.json`

**Compare:** system vs teacher — grades, criteria, runtime, replay.

**After labels filled:**
```powershell
.venv\Scripts\python.exe tools\run_institutional_closure.py
```

**Metrics:** Cohen's Kappa, disagreement rate, FP/FN — in `kappa_report.json`.

---

## Phase 3 — Runtime-Ready Submission Policy

**Document:** `app/calibration/RUNTIME_READY_SUBMISSION_POLICY_ar.md`

Communicate to students **before** next batch upload.

---

## Phase 4 — Governance Freeze Sign-off

**Artifacts:**
- `app/calibration/governance_release_v1.json`
- `app/calibration/reports/closure/rubric_freeze_v1.json`
- `app/calibration/reports/closure/GOVERNANCE_SIGNOFF_v1.json`

**Requires:** teacher + admin + QA signatures — `PENDING_HUMAN_VALIDATION`.

---

## Phase 5 — Controlled Deployment

- One assignment
- Limited batch
- Live monitoring
- Real appeals
- Replay audits weekly

**Not:** full autonomous deployment.

---

## Phase 6 — Drift Monitoring (ongoing)

**Tools:**
- `GET /api/metrics`
- `app/drift/drift_monitor.py`
- Re-run closure monthly: `tools/run_institutional_closure.py`

---

## Phase 7 — Appeals & Review Workflow

**Scaffold:** `app/calibration/reports/closure/APPEALS_WORKFLOW_v1.json`

Student must access: replay summary, evidence inventory, human review request.

---

## Phase 8 — Institutional Trust Build-up

Built over time via:
- Stable replay (currently 25/25)
- Moderation success
- Low false-positive rate
- Consistent conservative P5/P6

**Target:** Defensible Institutional Deployment — not 100% certainty.

---

## Master command

```powershell
.venv\Scripts\python.exe tools\run_institutional_closure.py
```

**Manifest:** `app/calibration/reports/closure/CLOSURE_MANIFEST.json`
