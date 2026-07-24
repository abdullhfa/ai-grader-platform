"""Readiness contract for the isolated GameMaker Windows runtime provider."""
from __future__ import annotations

import importlib
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class SandboxReadiness:
    provider_name: str
    provider_configured: bool
    provider_reachable: bool
    disposable_environment_created: bool
    artifact_mount_ready: bool
    capture_pipeline_ready: bool
    ready: bool
    reason_code: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@runtime_checkable
class GameMakerSandboxProvider(Protocol):
    """Approved isolated executor; it exclusively owns EXE process creation."""
    name: str
    def readiness(self, *, executable: Path, submission_root: Optional[Path]) -> SandboxReadiness: ...
    def launch_and_observe(self, *, executable: Path, runtime_cwd: Path, timeout_seconds: int,
                           session_context: Dict[str, Any]) -> Dict[str, Any]: ...


def _unavailable(reason_code: str, detail: str = "", *, provider_name: str = "unconfigured") -> SandboxReadiness:
    return SandboxReadiness(provider_name, False, False, False, False, False, False, reason_code, detail)


def resolve_gamemaker_sandbox_provider() -> tuple[Optional[GameMakerSandboxProvider], SandboxReadiness]:
    """Load a configured provider. There is deliberately no host fallback."""
    flag = os.environ.get("AI_GRADER_WINDOWS_SANDBOX", "").strip()
    adapter_path = os.environ.get("AI_GRADER_GAMEMAKER_SANDBOX_ADAPTER", "").strip()
    provider_name = os.environ.get("AI_GRADER_GAMEMAKER_SANDBOX_PROVIDER", "").strip() or "unconfigured"
    if sys.platform != "win32":
        return None, _unavailable("RUNTIME_ENVIRONMENT_UNSUPPORTED", "platform_not_windows", provider_name=provider_name)
    if flag != "1":
        return None, _unavailable("RUNTIME_ENVIRONMENT_UNSUPPORTED", "windows_sandbox_feature_disabled", provider_name=provider_name)
    if not adapter_path or ":" not in adapter_path:
        return None, _unavailable("RUNTIME_ENVIRONMENT_UNSUPPORTED", "windows_sandbox_adapter_not_configured", provider_name=provider_name)
    module_name, factory_name = adapter_path.split(":", 1)
    try:
        provider = getattr(importlib.import_module(module_name), factory_name)()
    except Exception as exc:
        return None, _unavailable("RUNTIME_ENVIRONMENT_UNSUPPORTED", f"windows_sandbox_adapter_unavailable:{type(exc).__name__}", provider_name=provider_name)
    if not isinstance(provider, GameMakerSandboxProvider):
        return None, _unavailable("RUNTIME_ENVIRONMENT_UNSUPPORTED", "windows_sandbox_adapter_contract_invalid", provider_name=provider_name)
    return provider, SandboxReadiness(str(getattr(provider, "name", provider_name)), True, False, False, False, False, False, "READINESS_PENDING")


def assess_gamemaker_sandbox_readiness(*, executable: Path, submission_root: Optional[Path],
                                       provider: Optional[GameMakerSandboxProvider] = None) -> tuple[Optional[GameMakerSandboxProvider], SandboxReadiness]:
    """The enablement flag is insufficient: every isolation capability must be proven."""
    if provider is None:
        provider, fallback = resolve_gamemaker_sandbox_provider()
        if provider is None:
            return None, fallback
    try:
        readiness = provider.readiness(executable=executable, submission_root=submission_root)
    except Exception as exc:
        return provider, _unavailable("RUNTIME_ENVIRONMENT_UNSUPPORTED", f"windows_sandbox_readiness_failed:{type(exc).__name__}", provider_name=str(getattr(provider, "name", "configured")))
    required = (readiness.provider_configured, readiness.provider_reachable, readiness.disposable_environment_created,
                readiness.artifact_mount_ready, readiness.capture_pipeline_ready)
    if readiness.ready and all(required):
        return provider, readiness
    return provider, SandboxReadiness(readiness.provider_name, readiness.provider_configured, readiness.provider_reachable,
        readiness.disposable_environment_created, readiness.artifact_mount_ready, readiness.capture_pipeline_ready,
        False, readiness.reason_code or "RUNTIME_ENVIRONMENT_UNSUPPORTED", readiness.detail)
