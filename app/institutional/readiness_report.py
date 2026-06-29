"""Institutional readiness report — deployment and compliance checklist."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.production_config import get_production_config
from app.governance_freeze_registry import build_freeze_registry_report, get_l4_gate_status


def build_institutional_readiness_report(db=None, *, batch_id: int | None = None) -> Dict[str, Any]:
    cfg = get_production_config()
    checks: List[Dict[str, Any]] = []

    def _check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    _check("production_config_loaded", True, cfg.environment)
    _check("l4_gate_configured", get_l4_gate_status().get("l4_sandbox_permitted") is not None, "gate readable")
    _check("audit_log_path", bool(cfg.audit_log_path), cfg.audit_log_path)
    _check("deterministic_rubric_enabled", cfg.enable_deterministic_rubric, "deterministic rubric")
    _check("ai_reliability_enabled", cfg.enable_ai_reliability_layer, "AI reliability layer")

    submission_count = 0
    graded_count = 0
    if db is not None:
        try:
            from app.models import GradingSummary, Submission

            q = db.query(Submission)
            if batch_id is not None:
                q = q.filter(Submission.batch_id == batch_id)
            submission_count = q.count()
            graded_count = (
                db.query(GradingSummary)
                .join(Submission, Submission.id == GradingSummary.submission_id)
            )
            if batch_id is not None:
                graded_count = graded_count.filter(Submission.batch_id == batch_id)
            graded_count = graded_count.count()
            _check("submissions_in_scope", submission_count >= 0, f"count={submission_count}")
            _check("graded_summaries", graded_count >= 0, f"graded={graded_count}")
        except Exception as exc:
            _check("database_accessible", False, str(exc))
    else:
        _check("database_accessible", False, "no db session")

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)
    return {
        "report_type": "institutional_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "readiness_score": round(passed / max(total, 1) * 100, 1),
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "governance_freeze": build_freeze_registry_report(),
        "production_config": {
            "environment": cfg.environment,
            "enable_l4_sandbox": cfg.enable_l4_sandbox,
            "rate_limit_per_minute": cfg.rate_limit_per_minute,
        },
        "interpretation_ar": (
            "تقرير جاهزية مؤسسية — يقيّم البنية التحتية وليس صحة كل درجة على حدة."
        ),
    }
