"""Terminal failure taxonomy for Godot PRO runtime observation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

FAILURE_CODES = (
    "BOOT_TIMEOUT",
    "BLACK_SCREEN_PERSISTENT",
    "MENU_NOT_RESOLVED",
    "WINDOW_NOT_FOUND",
    "GAME_WINDOW_CAPTURE_FAILED",
    "NO_VISUAL_RESPONSE_TO_INPUT",
    "SERVER_DEPENDENCY_BLOCK",
    "PROCESS_CRASHED",
    "GAMEPLAY_ENTERED_BUT_NO_MECHANICS",
)

_LABELS_AR: Dict[str, str] = {
    "BOOT_TIMEOUT": "انتهت مهلة الإقلاع — الشاشة لم تنتقل من التحميل/السواد.",
    "BLACK_SCREEN_PERSISTENT": "شاشة سوداء مستمرة بعد polling كامل.",
    "MENU_NOT_RESOLVED": "قائمة/start screen لم تُحل إلى gameplay.",
    "WINDOW_NOT_FOUND": "تعذّر العثور على نافذة اللعبة أو التقاطها.",
    "GAME_WINDOW_CAPTURE_FAILED": (
        "تعذّر التقاط نافذة اللعبة للتحقق — اللعبة تعمل لكن Agent لم يحصل على لقطة gameplay صالحة."
    ),
    "NO_VISUAL_RESPONSE_TO_INPUT": "لا استجابة بصرية للإدخال بعد burst التفاعل.",
    "SERVER_DEPENDENCY_BLOCK": "حوار شبكة/خادم يمنع اللعب (Connection Failed).",
    "PROCESS_CRASHED": "عملية اللعبة انتهت أثناء المراقبة.",
    "GAMEPLAY_ENTERED_BUT_NO_MECHANICS": "دخل gameplay لكن لم تُثبت أي ميكانيكا.",
}


@dataclass(frozen=True)
class GodotRuntimeFailure:
    code: str
    reason_ar: str
    reason_en: str
    evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_capture_failure(
    *,
    window_detected: bool,
    process_alive: bool,
    capture_scope_last: str = "",
    capture_retries_exhausted: bool = True,
    probe_phase: str = "tagged_capture",
    requirement_id: str = "",
    phase: str = "",
) -> GodotRuntimeFailure:
    """PRO capture pipeline failed despite running process (orthogonal to visual_response)."""
    evidence: Dict[str, Any] = {
        "window_detected": window_detected,
        "process_alive": process_alive,
        "capture_scope_last": capture_scope_last,
        "capture_retries_exhausted": capture_retries_exhausted,
        "probe_phase": probe_phase,
        "requirement_id": requirement_id,
        "phase": phase,
    }
    return _fail("GAME_WINDOW_CAPTURE_FAILED", evidence)


def classify_runtime_failure(
    *,
    window_detected: bool,
    black_screen_duration_s: float,
    gameplay_entered: bool,
    mechanics_verified_count: int,
    menu_status: str,
    visual_response: bool,
    server_dialog_detected: bool,
    process_crashed: bool,
    boot_timed_out: bool,
    capture_scope_degraded: bool = False,
) -> Optional[GodotRuntimeFailure]:
    """Return one terminal failure code, or None when gameplay+mechanics succeeded.

    ``capture_scope_degraded=True`` means the run has desktop_fallback captures and
    no valid game_window capture — the agent went blind mid-run (window closed or
    capture lost). In that state NO_VISUAL_RESPONSE_TO_INPUT would falsely blame
    the student's game, so the failure is GAME_WINDOW_CAPTURE_FAILED instead.
    """
    evidence: Dict[str, Any] = {
        "window_detected": window_detected,
        "black_screen_duration_s": black_screen_duration_s,
        "gameplay_entered": gameplay_entered,
        "mechanics_verified_count": mechanics_verified_count,
        "menu_status": menu_status,
        "visual_response": visual_response,
        "server_dialog_detected": server_dialog_detected,
        "process_crashed": process_crashed,
        "boot_timed_out": boot_timed_out,
        "capture_scope_degraded": capture_scope_degraded,
    }
    if gameplay_entered and mechanics_verified_count >= 1:
        return None
    if process_crashed:
        return _fail("PROCESS_CRASHED", evidence)
    if server_dialog_detected:
        return _fail("SERVER_DEPENDENCY_BLOCK", evidence)
    if not window_detected:
        return _fail("WINDOW_NOT_FOUND", evidence)
    if gameplay_entered and mechanics_verified_count == 0:
        return _fail("GAMEPLAY_ENTERED_BUT_NO_MECHANICS", evidence)
    if boot_timed_out:
        return _fail("BOOT_TIMEOUT", evidence)
    if black_screen_duration_s >= 20:
        return _fail("BLACK_SCREEN_PERSISTENT", evidence)
    status = (menu_status or "").lower()
    if not gameplay_entered:
        # Capture-pipeline failures (e.g. capture_preflight_failed, capture_failed)
        # mean the agent was BLIND — it never observed the game, so the game's
        # responsiveness is unknown. Classifying these as NO_VISUAL_RESPONSE_TO_INPUT
        # falsely blames the student's game for an environment/capture problem.
        if capture_scope_degraded:
            return _fail("GAME_WINDOW_CAPTURE_FAILED", evidence)
        if "capture" in status and ("fail" in status or "preflight" in status):
            return _fail("GAME_WINDOW_CAPTURE_FAILED", evidence)
        if "menu" in status:
            return _fail("MENU_NOT_RESOLVED", evidence)
        if status in ("loading", "black_screen", "unknown") and black_screen_duration_s > 10:
            return _fail("BLACK_SCREEN_PERSISTENT", evidence)
        if not visual_response:
            return _fail("NO_VISUAL_RESPONSE_TO_INPUT", evidence)
        return _fail("MENU_NOT_RESOLVED", evidence)
    return None


def _fail(code: str, evidence: Dict[str, Any]) -> GodotRuntimeFailure:
    return GodotRuntimeFailure(
        code=code,
        reason_ar=_LABELS_AR[code],
        reason_en=code.replace("_", " ").lower(),
        evidence=evidence,
    )
