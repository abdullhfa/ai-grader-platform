"""Windows Sandbox executor for GameMaker EXEs.

This adapter deliberately has no host-process fallback.  It is only ready after
Windows Sandbox has completed an in-guest probe that writes a marker and a
capture into a dedicated evidence mount.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

from .sandbox_provider import SandboxReadiness


_PROBE_TIMEOUT_SECONDS = 45


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class WindowsSandboxGameMakerProvider:
    """Runs an EXE through WindowsSandbox.exe and reads guest-written evidence."""

    name = "windows-sandbox"

    def __init__(self, *, sandbox_executable: str | None = None, work_root: Path | None = None) -> None:
        configured = os.environ.get("AI_GRADER_WINDOWS_SANDBOX_EXECUTABLE", "").strip()
        self._sandbox_executable = sandbox_executable or configured or shutil.which("WindowsSandbox.exe")
        root = os.environ.get("AI_GRADER_WINDOWS_SANDBOX_WORK_ROOT", "").strip()
        self._work_root = work_root or (Path(root) if root else Path(tempfile.gettempdir()) / "ai-grader-windows-sandbox")
        self._guest_runner = Path(__file__).with_name("windows_sandbox_guest_runner.ps1")

    def readiness(self, *, executable: Path, submission_root: Optional[Path]) -> SandboxReadiness:
        if not _truthy(os.environ.get("AI_GRADER_WINDOWS_SANDBOX")):
            return self._not_ready("windows_sandbox_feature_disabled")
        if not self._sandbox_executable or not Path(self._sandbox_executable).is_file():
            return self._not_ready("windows_sandbox_executable_not_found")
        if not self._guest_runner.is_file():
            return self._not_ready("windows_sandbox_guest_runner_missing")
        if not _truthy(os.environ.get("AI_GRADER_WINDOWS_SANDBOX_PROBE")):
            return self._not_ready("windows_sandbox_probe_not_authorized", configured=True, reachable=True)
        return self._probe()

    def launch_and_observe(self, *, executable: Path, runtime_cwd: Path, timeout_seconds: int,
                           session_context: dict[str, Any]) -> dict[str, Any]:
        """Launch only through the guest; no executable is ever started on the host."""
        session_dir = self._new_session_dir()
        source_dir, evidence_dir = session_dir / "source", session_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(runtime_cwd, source_dir, dirs_exist_ok=False)
            relative_exe = executable.resolve().relative_to(runtime_cwd.resolve())
            config = self._write_config(source_dir, evidence_dir, relative_exe, timeout_seconds, probe=False)
            proc = subprocess.Popen([str(self._sandbox_executable), str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = self._wait_for_result(evidence_dir, timeout_seconds + 20)
            if result is None:
                return {"attempted": True, "smoke_result": "timeout", "errors": ["sandbox_result_timeout"],
                        "signals": {"sandbox_host_pid": proc.pid}, "runtime_screenshots": []}
            screenshots = [{"path": str(path), "status": "captured", "capture_scope": "sandbox_guest"}
                           for path in sorted(evidence_dir.glob("*.png")) if path.stat().st_size > 0]
            status = str(result.get("status") or "error")
            return {"attempted": True, "smoke_result": "stable_window" if status == "completed" and screenshots else "launch_ok" if status == "completed" else status,
                    "runtime_screenshots": screenshots, "signals": result, "errors": result.get("errors") or []}
        except Exception as exc:
            return {"attempted": False, "smoke_result": "error", "errors": [f"windows_sandbox_adapter:{type(exc).__name__}"]}

    def _probe(self) -> SandboxReadiness:
        session_dir = self._new_session_dir()
        evidence_dir = session_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        try:
            config = self._write_config(session_dir / "source", evidence_dir, Path("probe.exe"), _PROBE_TIMEOUT_SECONDS, probe=True)
            subprocess.Popen([str(self._sandbox_executable), str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = self._wait_for_result(evidence_dir, _PROBE_TIMEOUT_SECONDS)
            capture_ok = any(path.stat().st_size > 0 for path in evidence_dir.glob("*.png"))
            if result and result.get("status") == "probe_completed" and capture_ok:
                return SandboxReadiness(self.name, True, True, True, True, True, True, "READY")
            return self._not_ready("windows_sandbox_probe_failed", configured=True, reachable=True)
        except Exception as exc:
            return self._not_ready(f"windows_sandbox_probe_failed:{type(exc).__name__}", configured=True, reachable=True)

    def _not_ready(self, detail: str, *, configured: bool = False, reachable: bool = False) -> SandboxReadiness:
        return SandboxReadiness(self.name, configured, reachable, False, False, False, False,
                                "RUNTIME_ENVIRONMENT_UNSUPPORTED", detail)

    def _new_session_dir(self) -> Path:
        directory = self._work_root / f"session-{uuid.uuid4().hex}"
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def _write_config(self, source_dir: Path, evidence_dir: Path, executable: Path, timeout_seconds: int, *, probe: bool) -> Path:
        source_dir.mkdir(parents=True, exist_ok=True)
        config = evidence_dir.parent / "session.wsb"
        guest_source = f"C:\\Users\\WDAGUtilityAccount\\Desktop\\{source_dir.name}"
        guest_evidence = f"C:\\Users\\WDAGUtilityAccount\\Desktop\\{evidence_dir.name}"
        command = (f'powershell.exe -ExecutionPolicy Bypass -File "{guest_source}\\windows_sandbox_guest_runner.ps1" '
                   f'-EvidenceDir "{guest_evidence}" -TimeoutSeconds {int(timeout_seconds)} '
                   f'-ExecutableRelativePath "{executable.as_posix()}"' + (" -Probe" if probe else ""))
        if not probe:
            shutil.copy2(self._guest_runner, source_dir / self._guest_runner.name)
        else:
            shutil.copy2(self._guest_runner, source_dir / self._guest_runner.name)
        xml = f'''<Configuration><VGpu>Disable</VGpu><Networking>Disable</Networking><ClipboardRedirection>Disable</ClipboardRedirection><MappedFolders>
<MappedFolder><HostFolder>{escape(str(source_dir.resolve()))}</HostFolder><ReadOnly>true</ReadOnly></MappedFolder>
<MappedFolder><HostFolder>{escape(str(evidence_dir.resolve()))}</HostFolder><ReadOnly>false</ReadOnly></MappedFolder>
</MappedFolders><LogonCommand><Command>{escape(command)}</Command></LogonCommand></Configuration>'''
        config.write_text(xml, encoding="utf-8")
        return config

    @staticmethod
    def _wait_for_result(evidence_dir: Path, timeout_seconds: int) -> dict[str, Any] | None:
        result_path = evidence_dir / "result.json"
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if result_path.is_file():
                try:
                    return json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            time.sleep(0.5)
        return None


def create_windows_sandbox_provider() -> WindowsSandboxGameMakerProvider:
    return WindowsSandboxGameMakerProvider()
