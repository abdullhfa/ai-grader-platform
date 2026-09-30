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
    EXECUTABLE_MISSING: (
        "No executable or buildable project was submitted.",
        "MISSING_ARTIFACT",
        "upload",
    ),
}


def pause_for(session, code: str) -> None:
    detail, kind, resolvable_by = BLOCKER_CATALOG[code]
    session.pause(code, detail, kind=kind, resolvable_by=resolvable_by)
