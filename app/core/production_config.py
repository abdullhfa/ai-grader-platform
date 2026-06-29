"""
Central production configuration — separates experimental from production paths.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import FrozenSet


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ProductionConfig:
    """Immutable production flags — read once at startup."""

    environment: str = "production"
    enable_l4_sandbox: bool = True
    enable_experimental_calibration_ui: bool = False
    sandbox_timeout_seconds: int = 12
    sandbox_max_artifacts: int = 6
    grading_max_retries: int = 2
    rate_limit_per_minute: int = 120
    strict_evidence_gate: bool = False
    auto_sync_runtime_adjudication: bool = True
    enable_ai_reliability_layer: bool = True
    enable_deterministic_rubric: bool = True
    enable_visual_verification: bool = True
    audit_log_path: str = "uploads/audit/production_audit.jsonl"
    allowed_sandbox_extensions: FrozenSet[str] = field(
        default_factory=lambda: frozenset(
            {".exe", ".apk", ".pck", ".py", ".html", ".htm", ".js", ".wasm"}
        )
    )

    @classmethod
    def from_env(cls) -> ProductionConfig:
        env_name = os.environ.get("AI_GRADER_ENV", "production").strip().lower()
        return cls(
            environment=env_name,
            enable_l4_sandbox=_env_bool("AI_GRADER_ENABLE_L4", True),
            enable_experimental_calibration_ui=_env_bool(
                "AI_GRADER_EXPERIMENTAL_UI", env_name != "production"
            ),
            sandbox_timeout_seconds=_env_int("AI_GRADER_SANDBOX_TIMEOUT", 12),
            sandbox_max_artifacts=_env_int("AI_GRADER_SANDBOX_MAX_ARTIFACTS", 6),
            grading_max_retries=_env_int("AI_GRADER_GRADING_RETRIES", 2),
            rate_limit_per_minute=_env_int("AI_GRADER_RATE_LIMIT", 120),
            strict_evidence_gate=_env_bool("AI_GRADER_STRICT_EVIDENCE_GATE", False),
            auto_sync_runtime_adjudication=_env_bool("AI_GRADER_AUTO_RUNTIME_SYNC", True),
            enable_ai_reliability_layer=_env_bool("AI_GRADER_AI_RELIABILITY", True),
            enable_deterministic_rubric=_env_bool("AI_GRADER_DETERMINISTIC_RUBRIC", True),
            enable_visual_verification=_env_bool("AI_GRADER_VISUAL_VERIFY", True),
            audit_log_path=os.environ.get(
                "AI_GRADER_AUDIT_LOG", "uploads/audit/production_audit.jsonl"
            ),
        )

    def is_production(self) -> bool:
        return self.environment == "production"


def resolve_sandbox_timeout_seconds(grading_mode: str | None = None) -> int:
    """
    PRO/deep: 30–45s smoke window (default 40) — enough for P6/P7 gameplay signals.
    FAST/basic: 12s — keeps batch throughput.
    Override: AI_GRADER_SANDBOX_TIMEOUT (all modes) or AI_GRADER_SANDBOX_TIMEOUT_PRO (PRO only).
    """
    cfg = get_production_config()
    try:
        from app.grading_mode_policy import is_fast_grading_mode

        fast = is_fast_grading_mode(grading_mode)
    except Exception:
        fast = (grading_mode or "").strip().lower() in ("fast", "basic")

    if fast:
        return min(cfg.sandbox_timeout_seconds, _env_int("AI_GRADER_SANDBOX_TIMEOUT_FAST", 12))

    pro_timeout = _env_int("AI_GRADER_SANDBOX_TIMEOUT_PRO", 40)
    pro_max = _env_int("AI_GRADER_SANDBOX_TIMEOUT_MAX", 45)
    pro_min = _env_int("AI_GRADER_SANDBOX_TIMEOUT_PRO_MIN", 30)
    if os.environ.get("AI_GRADER_SANDBOX_TIMEOUT", "").strip().isdigit():
        return max(pro_min, min(int(os.environ["AI_GRADER_SANDBOX_TIMEOUT"]), pro_max))
    return max(pro_min, min(pro_timeout, pro_max))


@lru_cache(maxsize=1)
def get_production_config() -> ProductionConfig:
    return ProductionConfig.from_env()
