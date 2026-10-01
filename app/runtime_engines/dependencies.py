"""Machine-readable blocker codes for missing grader-side dependencies.

"Cannot run" is never "not achieved": an engine that lacks its toolchain PAUSES
the session with one of these codes instead of degrading to static analysis and
reporting COMPLETED.  Resolving the blocker (install / upload) lets the pipeline
resume from the runtime phase.
"""
from __future__ import annotations

from typing import Dict, Tuple

UNITY_EDITOR_MISSING = "unity_editor_missing"
UNITY_AUTO_BUILD_DISABLED = "unity_auto_build_disabled"
UNITY_LICENSE_FAULT = "unity_license_or_activation_fault"
GODOT_BINARY_MISSING = "godot_binary_missing"
NODE_MISSING = "node_runtime_missing"
EXECUTABLE_MISSING = "executable_not_found"
WINDOWS_LAUNCHER_MISSING = "windows_exe_launcher_unavailable"
EMULATOR_RUN_FAULT = "windows_emulator_run_fault"

# code -> (English detail for logs/UI, blocker kind, resolvable_by)
BLOCKER_CATALOG: Dict[str, Tuple[str, str, str]] = {
    UNITY_EDITOR_MISSING: (
        "Unity Editor is required but not installed (set AI_GRADER_UNITY_BIN).",
        "MISSING_DEPENDENCY",
        "install",
    ),
    UNITY_AUTO_BUILD_DISABLED: (
        "The submission has Unity source only and temporary builds are disabled "
        "(AI_GRADER_UNITY_AUTO_BUILD=0).",
        "MISSING_DEPENDENCY",
        "install",
    ),
    UNITY_LICENSE_FAULT: (
        "Unity Editor could not build: license/activation fault on the grader.",
        "ENV_FAULT",
        "retry",
    ),
    GODOT_BINARY_MISSING: (
        "Godot binary is required but not installed (set AI_GRADER_GODOT_BIN).",
        "MISSING_DEPENDENCY",
        "install",
    ),
    NODE_MISSING: (
        "Node.js with scratch-vm is required to run the Scratch project but is not installed.",
        "MISSING_DEPENDENCY",
        "install",
    ),
    WINDOWS_LAUNCHER_MISSING: (
        "A Windows executable exists but this host cannot launch it "
        "(Windows launcher unavailable); the game was not run.",
        "MISSING_DEPENDENCY",
        "install",
    ),
    EMULATOR_RUN_FAULT: (
        "The game could not be run reliably on this host's Windows emulator "
        "(Wine); a crash inside the emulator is not a verdict on the student's game. "
        "A native Windows or fully compatible host is required.",
        "ENV_FAULT",
        "install",
    ),
    EXECUTABLE_MISSING: (
        "No executable or buildable project was submitted.",
        "MISSING_ARTIFACT",
        "upload",
    ),
}


def launcher_status() -> dict:
    """Can THIS host actually start a Windows .exe? ``{"ok": bool, "reason": str}``.

    Windows hosts launch natively.  Elsewhere the host must pass a *real* Wine
    probe (a Windows process really starts on a virtual display) — Wine merely
    being installed is not enough.  "Cannot launch" is never "the game failed".
    """
    import sys

    if sys.platform == "win32":
        return {"ok": True, "reason": "native windows host"}
    from app.runtime_wine import probe_wine_launcher

    return probe_wine_launcher()


def can_launch_windows_exe() -> bool:
    return bool(launcher_status().get("ok"))


def pause_if_cannot_launch(session) -> bool:
    if can_launch_windows_exe():
        return False
    reason = str(launcher_status().get("reason") or "")
    detail, kind, resolvable_by = BLOCKER_CATALOG[WINDOWS_LAUNCHER_MISSING]
    session.pause(
        WINDOWS_LAUNCHER_MISSING,
        f"{detail} [{reason}]" if reason else detail,
        kind=kind,
        resolvable_by=resolvable_by,
    )
    return True


def pause_for(session, code: str) -> None:
    detail, kind, resolvable_by = BLOCKER_CATALOG[code]
    session.pause(code, detail, kind=kind, resolvable_by=resolvable_by)


def pause_if_environment_fault(session, observation) -> bool:
    """A launcher/emulator fault means the game was not really run: PAUSE."""
    fault = (observation or {}).get("environment_fault")
    if not fault:
        return False
    detail, kind, resolvable_by = BLOCKER_CATALOG[EMULATOR_RUN_FAULT]
    tail = str((observation or {}).get("wine_stderr_tail") or "").strip()[-200:]
    session.pause(
        EMULATOR_RUN_FAULT,
        f"{detail} [{fault}{': ' + tail if tail else ''}]",
        kind=kind,
        resolvable_by=resolvable_by,
    )
    return True
