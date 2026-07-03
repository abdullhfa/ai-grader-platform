"""Godot-only retry orchestration: boot → nav#1 → play#1 → refocus → nav#2 → play#2 → classify."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.godot_runtime.failure_taxonomy import (
    GodotRuntimeFailure,
    classify_capture_failure,
    classify_runtime_failure,
)

CAPTURE_PROBE_MAX_ATTEMPTS = 5
CAPTURE_TAGGED_MAX_ATTEMPTS = 3
CAPTURE_RETRY_INTERVAL_S = 0.5

SERVER_DIALOG_MARKERS = (
    "connection failed",
    "failed to connect",
    "network error",
    "could not connect",
    "server unavailable",
    "unable to connect",
)


def is_godot_runtime_path(artifact_path: Path, *, engine_id: Optional[str] = None) -> bool:
    """True when PRO observation should use Godot retry policy."""
    eng = (engine_id or "").strip().lower()
    if eng in ("godot", "legacy_exe"):
        return True
    if artifact_path.suffix.lower() != ".exe":
        return False
    parent = artifact_path.parent
    stem = artifact_path.stem.lower()
    for name in ("game.pck", f"{artifact_path.stem}.pck", f"{stem}.pck"):
        if (parent / name).is_file():
            return True
    return False


def detect_server_dialog(shots: List[Dict[str, Any]]) -> bool:
    from app.gameplay_verifier import _shot_ocr_text

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        blob = _shot_ocr_text(shot).lower()
        if any(marker in blob for marker in SERVER_DIALOG_MARKERS):
            return True
    return False


def _collect_shots(nav_result: Any, package: Any) -> List[Dict[str, Any]]:
    shots: List[Dict[str, Any]] = []
    for key in ("screenshot", "entry_screenshot"):
        s = getattr(nav_result, key, None)
        if isinstance(s, dict):
            shots.append(s)
    nav_dict = nav_result.to_dict() if hasattr(nav_result, "to_dict") else {}
    for entry in nav_dict.get("log") or []:
        if isinstance(entry, dict) and isinstance(entry.get("screenshot"), dict):
            shots.append(entry["screenshot"])
    for s in getattr(package, "screenshots", None) or []:
        if isinstance(s, dict):
            shots.append(s)
    return shots


def _visual_response_from_package(package: Any) -> bool:
    for result in getattr(package, "results", None) or []:
        if getattr(result, "verified", False):
            return True
    return False


def _black_screen_duration_s(nav_result: Any) -> float:
    from app.gameplay_verifier import MenuNavigator

    nav_dict = nav_result.to_dict() if hasattr(nav_result, "to_dict") else {}
    status = str(nav_dict.get("status") or "")
    if status == "black_screen":
        return float(
            MenuNavigator.GODOT_BOOT_WAIT
            + MenuNavigator.BOOT_POLL_MAX * MenuNavigator.BOOT_POLL_INTERVAL
        )
    return 0.0


def _boot_timed_out(nav_result: Any) -> bool:
    nav_dict = nav_result.to_dict() if hasattr(nav_result, "to_dict") else {}
    return str(nav_dict.get("status") or "") == "black_screen"


def _is_valid_game_window_shot(shot: Dict[str, Any]) -> bool:
    return (
        isinstance(shot, dict)
        and shot.get("status") == "captured"
        and str(shot.get("capture_scope") or "") == "game_window"
    )


def probe_game_window_capture(
    *,
    artifact_path: Path,
    process_pid: Optional[int],
    capture_screenshot: Callable[..., Dict[str, Any]],
    elapsed_seconds: float,
    label_prefix: str = "capture_probe",
) -> tuple[bool, Dict[str, Any], int]:
    """Focus + capture probe; returns (ok, last_shot, attempts_used)."""
    from app.window_focus_manager import focus_game_window

    last_shot: Dict[str, Any] = {}
    for attempt in range(CAPTURE_PROBE_MAX_ATTEMPTS):
        try:
            focus_game_window(process_pid=process_pid)
        except Exception:
            pass
        last_shot = dict(
            capture_screenshot(
                artifact_path,
                label=f"{label_prefix}_{attempt}",
                elapsed_seconds=elapsed_seconds,
                process_pid=process_pid,
            )
            or {}
        )
        if _is_valid_game_window_shot(last_shot):
            return True, last_shot, attempt + 1
        if attempt + 1 < CAPTURE_PROBE_MAX_ATTEMPTS:
            time.sleep(CAPTURE_RETRY_INTERVAL_S)
    return False, last_shot, CAPTURE_PROBE_MAX_ATTEMPTS


@dataclass
class GodotRetryOutcome:
    nav_result: Any
    gameplay_entered: bool
    package: Any
    movement: Dict[str, Any]
    retry_attempts: List[Dict[str, Any]] = field(default_factory=list)
    failure: Optional[GodotRuntimeFailure] = None


class GodotRetryPolicy:
    """Fixed Godot sequence — not shared with Unity/GameMaker."""

    def run(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
        requirement_plan: Optional[Any] = None,
        pro_mode: bool = True,
        process_crashed: bool = False,
    ) -> GodotRetryOutcome:
        from app.gameplay_verifier import (
            EvidencePackage,
            MenuNavigationResult,
            MenuNavigator,
            PlaytestOrchestrator,
            calculate_l4_level,
        )
        from app.requirement_extractor import RequirementExtractor

        retry_attempts: List[Dict[str, Any]] = []
        nav = MenuNavigator(max_attempts=MenuNavigator.MAX_ATTEMPTS)
        plan = requirement_plan or RequirementExtractor().default_plan()

        if pro_mode:
            ok, last_shot, attempts_used = probe_game_window_capture(
                artifact_path=artifact_path,
                process_pid=process_pid,
                capture_screenshot=capture_screenshot,
                elapsed_seconds=elapsed_seconds,
            )
            if not ok:
                scope_last = str(last_shot.get("capture_scope") or "desktop_fallback")
                failure = classify_capture_failure(
                    window_detected=process_pid is not None,
                    process_alive=process_pid is not None,
                    capture_scope_last=scope_last,
                    capture_retries_exhausted=True,
                    probe_phase="pre_flight",
                )
                movement = {
                    "player_movement_verified": False,
                    "jump_detected": False,
                    "score_change_detected": False,
                    "mechanics_verified_count": 0,
                    "l4_level": "L3",
                    "automated_l4_level": "L3",
                }
                return GodotRetryOutcome(
                    nav_result=MenuNavigationResult(
                        status="capture_preflight_failed",
                        gameplay_entered=False,
                        visual_state="unknown",
                    ),
                    gameplay_entered=False,
                    package=EvidencePackage(),
                    movement=movement,
                    retry_attempts=[
                        {
                            "step": "capture_preflight",
                            "passed": False,
                            "attempts": attempts_used,
                        }
                    ],
                    failure=failure,
                )

        def _nav_pass(step: str, elapsed: float) -> Any:
            result = nav.navigate_to_gameplay(
                artifact_path=artifact_path,
                process_pid=process_pid,
                capture_screenshot=capture_screenshot,
                elapsed_seconds=elapsed,
            )
            retry_attempts.append(
                {
                    "step": step,
                    "gameplay_entered": bool(result.gameplay_entered),
                    "status": result.status,
                    "visual_state": result.visual_state,
                }
            )
            return result

        def _play_pass(step: str, elapsed: float, entered: bool) -> Any:
            pkg = PlaytestOrchestrator(pro_mode=pro_mode).run(
                artifact_path=artifact_path,
                process_pid=process_pid,
                capture_screenshot=capture_screenshot,
                plan=plan,
                elapsed_seconds=elapsed,
                gameplay_entered=entered,
            )
            mech = sum(1 for r in pkg.results if r.verified and r.req_id != "menu_navigation")
            retry_attempts.append(
                {
                    "step": step,
                    "gameplay_entered": bool(pkg.gameplay_entered),
                    "mechanics_verified_count": mech,
                }
            )
            return pkg

        nav_result = _nav_pass("nav_pass_1", elapsed_seconds)
        gameplay_entered = bool(nav_result.gameplay_entered)
        package = _play_pass("play_pass_1", elapsed_seconds + 2.0, gameplay_entered)
        gameplay_entered = bool(package.gameplay_entered or gameplay_entered)

        if not gameplay_entered:
            try:
                from app.window_focus_manager import focus_game_window

                focus_game_window(process_pid=process_pid)
            except Exception:
                pass
            time.sleep(MenuNavigator.GODOT_BOOT_WAIT)
            nav_result = _nav_pass(
                "nav_pass_2",
                elapsed_seconds + MenuNavigator.GODOT_BOOT_WAIT + 2.0,
            )
            gameplay_entered = bool(nav_result.gameplay_entered or gameplay_entered)
            package = _play_pass(
                "play_pass_2",
                elapsed_seconds + MenuNavigator.GODOT_BOOT_WAIT + 4.0,
                gameplay_entered,
            )
            gameplay_entered = bool(package.gameplay_entered or gameplay_entered)

        movement = package.to_movement_verification_dict()
        if not gameplay_entered:
            movement["player_movement_verified"] = False
            movement["jump_detected"] = False
            movement["score_change_detected"] = False
            movement["mechanics_verified_count"] = 0
            movement["l4_level"] = "L3"
            movement["automated_l4_level"] = "L3"
        else:
            l4_level = calculate_l4_level(
                gameplay_entered=True,
                mechanics_verified_count=int(movement.get("mechanics_verified_count") or 0),
            )
            movement["l4_level"] = l4_level
            movement["automated_l4_level"] = l4_level

        shots = _collect_shots(nav_result, package)
        mechanics_count = int(movement.get("mechanics_verified_count") or 0)
        failure = classify_runtime_failure(
            window_detected=process_pid is not None,
            black_screen_duration_s=_black_screen_duration_s(nav_result),
            gameplay_entered=gameplay_entered,
            mechanics_verified_count=mechanics_count,
            menu_status=str(nav_result.status or nav_result.visual_state or ""),
            visual_response=_visual_response_from_package(package),
            server_dialog_detected=detect_server_dialog(shots),
            process_crashed=process_crashed,
            boot_timed_out=_boot_timed_out(nav_result),
        )
        if failure is None and gameplay_entered and mechanics_count == 0:
            failure = classify_runtime_failure(
                window_detected=process_pid is not None,
                black_screen_duration_s=0,
                gameplay_entered=True,
                mechanics_verified_count=0,
                menu_status=str(nav_result.status or ""),
                visual_response=_visual_response_from_package(package),
                server_dialog_detected=False,
                process_crashed=False,
                boot_timed_out=False,
            )

        return GodotRetryOutcome(
            nav_result=nav_result,
            gameplay_entered=gameplay_entered,
            package=package,
            movement=movement,
            retry_attempts=retry_attempts,
            failure=failure,
        )
