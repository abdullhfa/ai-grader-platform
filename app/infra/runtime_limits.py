"""Per-session runtime resource limits — Phase 5 production hardening."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RuntimeResourceLimits:
    cpu_limit: float = 2.0
    memory_limit_mb: int = 2048
    gpu_limit: int = 0
    timeout_seconds: int = 120
    network_policy: str = "deny"
    disk_quota_mb: int = 512

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_limit": self.cpu_limit,
            "memory_limit_mb": self.memory_limit_mb,
            "gpu_limit": self.gpu_limit,
            "timeout_seconds": self.timeout_seconds,
            "network_policy": self.network_policy,
            "disk_quota_mb": self.disk_quota_mb,
        }

    def docker_flags(self) -> list[str]:
        """Docker CLI resource flags for ephemeral sandbox containers."""
        flags = [
            "--cpus",
            str(self.cpu_limit),
            "--memory",
            f"{self.memory_limit_mb}m",
            "--pids-limit",
            "256",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
        ]
        if self.network_policy == "deny":
            flags.extend(["--network", "none"])
        return flags


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def get_runtime_limits(profile: Optional[str] = None) -> RuntimeResourceLimits:
    """Resolve limits from env; optional profile suffix (unity, cv, web)."""
    suffix = ""
    if profile:
        suffix = f"_{profile.upper()}"

    def _get(name: str, default: int | float) -> int | float:
        key = f"AI_GRADER{suffix}_{name}" if suffix else f"AI_GRADER_{name}"
        if suffix and os.environ.get(key) is None:
            key = f"AI_GRADER_{name}"
        if isinstance(default, float):
            return _env_float(key, default)
        return _env_int(key, default)

    return RuntimeResourceLimits(
        cpu_limit=float(_get("RUNTIME_CPU_LIMIT", 2.0)),
        memory_limit_mb=int(_get("RUNTIME_MEMORY_MB", 2048)),
        gpu_limit=int(_get("RUNTIME_GPU_LIMIT", 0)),
        timeout_seconds=int(_get("RUNTIME_TIMEOUT", 120)),
        network_policy=os.environ.get("AI_GRADER_RUNTIME_NETWORK", "deny"),
        disk_quota_mb=int(_get("RUNTIME_DISK_MB", 512)),
    )
