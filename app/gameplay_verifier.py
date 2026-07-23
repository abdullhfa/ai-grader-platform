"""Automated gameplay verification (MenuNavigator + movement) for PRO L4 without human."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

VISUAL_DELTA_L4_THRESHOLD = 0.05
MOVEMENT_SHIFT_THRESHOLD = 2.5
JUMP_SHIFT_THRESHOLD = 3.0
MENU_NAV_VERSION = "menu_navigator_v1"
MOVEMENT_VERIFY_VERSION = "player_movement_verifier_v1"
AUTOMATED_GAMEPLAY_VERSION = "automated_gameplay_verification_v1"

MENU_KEYWORDS = (
    "play",
    "start",
    "begin",
    "new game",
    "ابدأ",
    "العب",
    "اضغط",
    "press",
)
MENU_VISUAL_STATES = frozenset({"main_menu_candidate", "static_ui", "loading_screen"})
MENU_NAV_WINDOW_LOST = "window_lost"
HUD_KEYWORDS = (
    "score",
    "points",
    "coins",
    "health",
    "hp",
    "lives",
    "time",
    "timer",
    "level",
    "wave",
    "نقاط",
    "وقت",
    "حياة",
)


def _observation_from(
    observation: Optional[Dict[str, Any]],
    inventory: Optional[Dict[str, Any]],
    grading_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if isinstance(observation, dict) and observation:
        return observation
    inv = inventory if isinstance(inventory, dict) else {}
    if isinstance(inv.get("runtime_observation_report"), dict):
        return inv["runtime_observation_report"]
    if isinstance(grading_result, dict) and isinstance(
        grading_result.get("runtime_observation_report"), dict
    ):
        return grading_result["runtime_observation_report"]
    return {}


def _interaction_trace(obs: Dict[str, Any]) -> Dict[str, Any]:
    trace = obs.get("interaction_trace") or obs.get("runtime_interaction_trace") or {}
    if isinstance(trace, dict) and trace:
        return trace
    for row in obs.get("interaction_trace_summary") or obs.get("artifact_analyses") or []:
        if isinstance(row, dict) and row.get("interaction_trace"):
            return row["interaction_trace"]
        if isinstance(row, dict) and row.get("visual_delta_score") is not None:
            return row
    return {}


def _gameplay_verification_blob(
    observation: Optional[Dict[str, Any]] = None,
    *,
    inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inv = inventory if isinstance(inventory, dict) else {}
    if isinstance(inv.get("gameplay_verification"), dict):
        return inv["gameplay_verification"]
    obs = _observation_from(observation, inventory, grading_result)
    if isinstance(obs.get("gameplay_verification"), dict):
        return obs["gameplay_verification"]
    if isinstance(grading_result, dict) and isinstance(
        grading_result.get("gameplay_verification"), dict
    ):
        return grading_result["gameplay_verification"]
    trace = _interaction_trace(obs)
    if trace.get("l4_level") or trace.get("automated_l4_level"):
        return trace
    return {}


def _ocr_image_path(path: str) -> str:
    if not path or not Path(path).is_file():
        return ""
    try:
        from app.gameplay_ai.cv.text_ocr import ocr_frame

        row = ocr_frame(Path(path))
        return str(row.get("text") or "").lower()
    except Exception:
        return ""


def _menu_keywords_in_text(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in MENU_KEYWORDS)


def _hud_keywords_in_text(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in HUD_KEYWORDS)


def _center_band_shift(before_path: str, after_path: str) -> Tuple[float, float]:
    """Return (horizontal_shift, vertical_shift) on center 40% band."""
    if not before_path or not after_path:
        return 0.0, 0.0
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return 0.0, 0.0
    try:
        before = Image.open(before_path).convert("L")
        after = Image.open(after_path).convert("L")
        if before.size != after.size:
            after = after.resize(before.size)
        w, h = before.size
        left = int(w * 0.3)
        right = int(w * 0.7)
        top = int(h * 0.25)
        bottom = int(h * 0.75)
        b_band = before.crop((left, top, right, bottom)).resize((48, 48))
        a_band = after.crop((left, top, right, bottom)).resize((48, 48))
        b_px = list(b_band.getdata())
        a_px = list(a_band.getdata())
        h_shifts: List[float] = []
        for offset in range(-6, 7):
            if offset == 0:
                continue
            score = 0.0
            for y in range(48):
                for x in range(48):
                    nx = x + offset
                    if 0 <= nx < 48:
                        score += abs(int(b_px[y * 48 + x]) - int(a_px[y * 48 + nx]))
            h_shifts.append((abs(offset), score / (48 * 48)))
        best_h = max((s for _, s in h_shifts), default=0.0)
        v_shifts: List[float] = []
        for offset in range(-6, 7):
            if offset == 0:
                continue
            score = 0.0
            for y in range(48):
                for x in range(48):
                    ny = y + offset
                    if 0 <= ny < 48:
                        score += abs(int(b_px[y * 48 + x]) - int(a_px[ny * 48 + x]))
            v_shifts.append((abs(offset), score / (48 * 48)))
        best_v = max((s for _, s in v_shifts), default=0.0)
        return round(best_h, 3), round(best_v, 3)
    except OSError:
        return 0.0, 0.0


def _send_key_win(vk: int, *, hold_ms: int = 80) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        ULONG_PTR = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

        def _key(flags: int) -> INPUT:
            inp = INPUT()
            inp.type = 1
            inp.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
            return inp

        if not ctypes.windll.user32.SendInput(1, ctypes.byref(_key(0)), ctypes.sizeof(INPUT)):
            return False
        time.sleep(max(hold_ms, 20) / 1000.0)
        return bool(
            ctypes.windll.user32.SendInput(1, ctypes.byref(_key(0x0002)), ctypes.sizeof(INPUT))
        )
    except Exception:
        return False


def _key_hold(label: str, seconds: float) -> bool:
    vk_map = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "SPACE": 0x20, "ENTER": 0x0D}
    vk = vk_map.get(label.upper())
    if vk is None:
        return False
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        ULONG_PTR = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

        down = INPUT()
        down.type = 1
        down.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        up = INPUT()
        up.type = 1
        up.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0x0002, time=0, dwExtraInfo=0)
        if not ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT)):
            return False
        time.sleep(max(seconds, 0.1))
        return bool(ctypes.windll.user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT)))
    except Exception:
        return False


def _click_game_window_center(*, process_pid: Optional[int], artifact_path: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        from app.window_focus_manager import focus_game_window, resolve_game_window_bbox

        focus_game_window(process_pid=process_pid)
        bbox = resolve_game_window_bbox(artifact_path=artifact_path, process_pid=process_pid)
        if not bbox:
            return False
        left, top, right, bottom = bbox
        cx = left + (right - left) // 2
        cy = top + int((bottom - top) * 0.62)
        import ctypes

        ctypes.windll.user32.SetCursorPos(cx, cy)
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return True
    except Exception:
        return False


class MenuNavigator:
    """Detect menu screens and attempt to enter gameplay."""

    def __init__(self, *, max_attempts: int = 5) -> None:
        self.max_attempts = max_attempts

    def _is_menu_screen(self, shot: Dict[str, Any]) -> bool:
        state = str(shot.get("visual_state") or "")
        ocr = _ocr_image_path(str(shot.get("path") or ""))
        if state in MENU_VISUAL_STATES and not _hud_keywords_in_text(ocr):
            return True
        if _menu_keywords_in_text(ocr) and not _hud_keywords_in_text(ocr):
            return True
        return False

    def _is_gameplay_screen(self, shot: Dict[str, Any]) -> bool:
        state = str(shot.get("visual_state") or "")
        ocr = _ocr_image_path(str(shot.get("path") or ""))
        if state == "gameplay_candidate":
            return True
        if _hud_keywords_in_text(ocr) and not _menu_keywords_in_text(ocr):
            return True
        if str(shot.get("capture_scope") or "") == "game_window" and _hud_keywords_in_text(ocr):
            return True
        return False

    def detect_and_enter_gameplay(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        from app.window_focus_manager import focus_game_window

        log: List[Dict[str, Any]] = []
        last_shot: Optional[Dict[str, Any]] = None
        for attempt in range(self.max_attempts):
            focus_game_window(process_pid=process_pid)
            time.sleep(0.35)
            shot = capture_screenshot(
                artifact_path,
                label=f"menu_nav_{attempt}",
                elapsed_seconds=elapsed_seconds + attempt * 0.5,
                process_pid=process_pid,
            )
            last_shot = shot
            if "RUNTIME_CAPTURE_LOST" in (shot.get("errors") or []) or shot.get("capture_scope") == "capture_lost":
                return {
                    "status": MENU_NAV_WINDOW_LOST,
                    "reason_code": "RUNTIME_CAPTURE_LOST",
                    "attempts": attempt + 1,
                    "log": log,
                    "screenshot": shot,
                }
            if self._is_gameplay_screen(shot):
                return {
                    "status": "gameplay_entered",
                    "attempts": attempt + 1,
                    "log": log,
                    "screenshot": shot,
                }
            if self._is_menu_screen(shot) or attempt == 0:
                _send_key_win(0x0D)
                time.sleep(0.15)
                _send_key_win(0x20)
                _click_game_window_center(process_pid=process_pid, artifact_path=artifact_path)
                log.append(
                    {
                        "attempt": attempt,
                        "action": "menu_dismiss",
                        "visual_state": shot.get("visual_state"),
                    }
                )
                time.sleep(1.8)
                continue
            log.append({"attempt": attempt, "action": "observe", "visual_state": shot.get("visual_state")})
        return {
            "status": "stuck_in_menu" if last_shot and self._is_menu_screen(last_shot) else "unknown",
            "attempts": self.max_attempts,
            "log": log,
            "screenshot": last_shot,
        }


class PlayerMovementVerifier:
    """Verify player movement, jump, and HUD changes — not generic visual delta."""

    def verify(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        from app.window_focus_manager import focus_game_window

        focus_game_window(process_pid=process_pid)
        time.sleep(0.2)
        before_move = capture_screenshot(
            artifact_path,
            label="move_before",
            elapsed_seconds=elapsed_seconds,
            process_pid=process_pid,
        )
        _key_hold("D", 0.55)
        after_move = capture_screenshot(
            artifact_path,
            label="move_after",
            elapsed_seconds=elapsed_seconds + 0.6,
            process_pid=process_pid,
        )
        h_shift, _ = _center_band_shift(
            str(before_move.get("path") or ""),
            str(after_move.get("path") or ""),
        )
        movement = h_shift >= MOVEMENT_SHIFT_THRESHOLD

        before_jump = capture_screenshot(
            artifact_path,
            label="jump_before",
            elapsed_seconds=elapsed_seconds + 0.7,
            process_pid=process_pid,
        )
        _send_key_win(0x20, hold_ms=120)
        time.sleep(0.75)
        after_jump = capture_screenshot(
            artifact_path,
            label="jump_after",
            elapsed_seconds=elapsed_seconds + 1.5,
            process_pid=process_pid,
        )
        _, v_jump = _center_band_shift(
            str(before_jump.get("path") or ""),
            str(after_jump.get("path") or ""),
        )
        jump = v_jump >= JUMP_SHIFT_THRESHOLD

        score_before = _ocr_image_path(str(before_jump.get("path") or ""))
        _key_hold("D", 1.8)
        score_shot = capture_screenshot(
            artifact_path,
            label="score_probe",
            elapsed_seconds=elapsed_seconds + 3.5,
            process_pid=process_pid,
        )
        score_after = _ocr_image_path(str(score_shot.get("path") or ""))
        score_change = bool(score_after) and score_before != score_after

        mechanics = int(movement) + int(jump) + int(score_change)
        if mechanics >= 3:
            l4_level = "L4_full"
        elif mechanics >= 1:
            l4_level = "L4_partial"
        else:
            l4_level = "L3"

        return {
            "version": MOVEMENT_VERIFY_VERSION,
            "movement": movement,
            "jump": jump,
            "score_change": score_change,
            "horizontal_shift": h_shift,
            "vertical_shift": v_jump,
            "mechanics_verified_count": mechanics,
            "l4_level": l4_level,
            "automated_l4_level": l4_level,
            "player_movement_verified": movement,
            "jump_detected": jump,
            "score_change_detected": score_change,
            "screenshots": [before_move, after_move, before_jump, after_jump, score_shot],
        }


def run_automated_gameplay_verification(
    *,
    artifact_path: Path,
    process_pid: Optional[int],
    capture_screenshot: Callable[..., Dict[str, Any]],
    elapsed_seconds: float,
) -> Dict[str, Any]:
    """Menu navigation then movement verification — PRO automated L4 path."""
    nav_result: Dict[str, Any]
    try:
        from app.runtime_engines.gamemaker.menu_navigator import MenuNavResult, navigate_menu_deterministic
        from app.runtime_engines.gamemaker.project_probe import assess_gamemaker_exe_launch
        from app.window_focus_manager import resolve_game_window_bbox, resolve_game_window_handle
        is_gamemaker = bool(assess_gamemaker_exe_launch(artifact_path).get("is_gamemaker"))
        hwnd = resolve_game_window_handle(artifact_path=artifact_path, process_pid=process_pid)
        rect = resolve_game_window_bbox(artifact_path=artifact_path, process_pid=process_pid)
        if is_gamemaker and hwnd and rect:
            result = navigate_menu_deterministic(hwnd, rect)
            nav_result = {"status": "gameplay_entered" if result is MenuNavResult.GAMEPLAY_ENTERED else result.value.lower(), "result": result.value}
        elif is_gamemaker:
            nav_result = {"status": MENU_NAV_WINDOW_LOST, "result": MenuNavResult.WINDOW_LOST.value, "reason_code": "RUNTIME_CAPTURE_LOST"}
        else:
            raise LookupError("non_gamemaker_runtime")
    except LookupError:
        nav = MenuNavigator(max_attempts=5)
        nav_result = nav.detect_and_enter_gameplay(
            artifact_path=artifact_path, process_pid=process_pid, capture_screenshot=capture_screenshot, elapsed_seconds=elapsed_seconds,
        )
    except Exception:
        nav_result = {"status": MENU_NAV_WINDOW_LOST, "result": "WINDOW_LOST", "reason_code": "RUNTIME_CAPTURE_LOST"}
    gameplay_entered = nav_result.get("status") == "gameplay_entered"
    movement = (
        PlayerMovementVerifier().verify(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            elapsed_seconds=elapsed_seconds + 2.0,
        )
        if gameplay_entered
        else {"l4_level": "L3", "mechanics_verified_count": 0, "screenshots": []}
    )

    extra_shots = []
    if isinstance(nav_result.get("screenshot"), dict):
        extra_shots.append(nav_result["screenshot"])
    extra_shots.extend(movement.get("screenshots") or [])

    gameplay_window_shots = sum(
        1
        for s in extra_shots
        if isinstance(s, dict)
        and s.get("status") == "captured"
        and str(s.get("capture_scope") or "") == "game_window"
    )

    l4_level = str(movement.get("l4_level") or "L3")
    if gameplay_entered and l4_level == "L3" and movement.get("mechanics_verified_count", 0) >= 1:
        l4_level = "L4_partial"

    report: Dict[str, Any] = {
        "version": AUTOMATED_GAMEPLAY_VERSION,
        "mode": AUTOMATED_GAMEPLAY_VERSION,
        "authority": "automated_l4_verification",
        "platform": sys.platform,
        "status": "completed",
        "menu_navigation": nav_result,
        "gameplay_entered": gameplay_entered,
        "movement_verification": movement,
        "l4_level": l4_level,
        "automated_l4_level": l4_level,
        "player_movement_verified": bool(movement.get("player_movement_verified")),
        "jump_detected": bool(movement.get("jump_detected")),
        "score_change_detected": bool(movement.get("score_change_detected")),
        "mechanics_verified_count": int(movement.get("mechanics_verified_count") or 0),
        "gameplay_window_screenshots": gameplay_window_shots,
        "does_not_verify_gameplay": l4_level == "L3",
        "human_playtest_required": l4_level == "L3",
        "authority_note_ar": (
            "تحقق L4 آلي — MenuNavigator + حركة/قفز/HUD بدون مراجعة بشرية."
            if l4_level in ("L4_full", "L4_partial")
            else "إطلاق فقط (L3) — لم تُثبت ميكانيكا gameplay بعد تجاوز القائمة."
        ),
        "extra_screenshots": extra_shots,
    }
    return report


def build_gameplay_checks_from_verification(verification: Dict[str, Any]) -> Dict[str, Any]:
    """Map automated verification into Pearson gameplay_checks shape."""
    movement = verification.get("movement_verification") or verification
    return {
        "win_state": {"observed": False},
        "lose_state": {"observed": False},
        "scene_transition": {
            "observed": bool(verification.get("gameplay_entered")),
        },
        "score_hud": {
            "observed": bool(
                movement.get("score_change_detected") or verification.get("score_change_detected")
            ),
        },
        "player_movement": {
            "observed": bool(
                movement.get("player_movement_verified")
                or verification.get("player_movement_verified")
            ),
        },
        "jump_mechanic": {
            "observed": bool(
                movement.get("jump_detected") or verification.get("jump_detected")
            ),
        },
    }


def assess_automated_l4_gate(
    verification: Optional[Dict[str, Any]],
    *,
    test_document_present: bool = False,
    functional_smoke_pass: bool = False,
) -> Dict[str, Any]:
    """Criterion-level automated L4 gate decisions (no human)."""
    gv = verification or {}
    l4 = str(gv.get("l4_level") or gv.get("automated_l4_level") or "L3")
    mechanics = int(gv.get("mechanics_verified_count") or 0)
    shots = int(gv.get("gameplay_window_screenshots") or 0)
    movement = bool(gv.get("player_movement_verified"))
    delta = float(gv.get("visual_delta_score") or 0)

    l4_full = (
        functional_smoke_pass
        and movement
        and mechanics >= 2
        and shots >= 2
        and l4 == "L4_full"
    )
    l4_partial = (
        l4 in ("L4_full", "L4_partial")
        and (movement or mechanics >= 1 or bool(gv.get("gameplay_entered")))
    ) or (
        functional_smoke_pass
        and (
            l4 in ("L4_full", "L4_partial")
            or (mechanics >= 1 and shots >= 1)
            or (delta >= VISUAL_DELTA_L4_THRESHOLD and movement)
        )
    )

    return {
        "l4_level": l4,
        "l4_full": l4_full,
        "l4_partial": l4_partial and not l4_full,
        "criterion_pass": {
            "P5": l4_full or l4_partial,
            "P6": (l4_full or l4_partial) and test_document_present,
            "M3": l4_full and test_document_present,
            "D3": l4_full and test_document_present,
        },
        "summary_ar": (
            f"L4 آلي ({l4}) — ميكانيكا={mechanics} لقطات={shots}"
            if l4_partial or l4_full
            else "L3 — إطلاق بدون gameplay مؤكد"
        ),
    }


def _test_document_present(inventory: Dict[str, Any]) -> bool:
    assets = inventory.get("assets_detected") or inventory.get("evidence_completeness_gate", {}).get(
        "assets_detected"
    ) or {}
    if assets.get("word_pdf") or assets.get("testing_documentation"):
        return True
    paths = inventory.get("intake_relative_paths") or inventory.get("submission_paths") or []
    joined = "\n".join(str(p) for p in paths).lower()
    return any(
        token in joined
        for token in (
            "test plan",
            "bug log",
            "استبيان",
            "اختبار",
            "survey",
            "questionnaire",
            ".pdf",
            ".docx",
        )
    )


def resolve_gameplay_evidence_level(
    observation: Optional[Dict[str, Any]] = None,
    *,
    inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> str:
    """Return L1 (none) through L5 (human-confirmed gameplay)."""
    gv = _gameplay_verification_blob(observation, inventory=inventory, grading_result=grading_result)
    l4 = str(gv.get("l4_level") or gv.get("automated_l4_level") or "")
    if l4 == "L4_full":
        return "L4"
    if l4 == "L4_partial":
        return "L4"

    obs = _observation_from(observation, inventory, grading_result)
    inv = inventory if isinstance(inventory, dict) else {}

    if obs.get("human_playtest_verified") or obs.get("playtest_level") == "L5":
        return "L5"
    mv = inv.get("mechanics_verification") or (grading_result or {}).get("mechanics_verification")
    if isinstance(mv, dict) and str(mv.get("mechanics_level") or "") == "L5":
        return "L5"

    trace = _interaction_trace(obs)
    delta_raw = trace.get("visual_delta_score")
    delta: Optional[float] = None
    if delta_raw is not None:
        try:
            delta = float(delta_raw)
        except (TypeError, ValueError):
            delta = None

    if trace.get("player_movement_verified") and delta is not None and delta >= VISUAL_DELTA_L4_THRESHOLD:
        return "L4"

    gameplay_shots: list = []
    try:
        from app.runtime_screenshot_validation import filter_gameplay_screenshots

        shots = obs.get("runtime_screenshots") or []
        gameplay_shots = filter_gameplay_screenshots(
            [s for s in shots if isinstance(s, dict)]
        )
    except Exception:
        gameplay_shots = []

    if gameplay_shots and trace.get("player_movement_verified"):
        return "L4"

    status = str(obs.get("status") or "").lower()
    if (
        obs.get("runtime_observed")
        or obs.get("runtime_verified")
        or status in ("completed", "partial", "error")
    ):
        return "L3"

    exe_files = (inv.get("executable_artifacts") or {}).get("files") or []
    if exe_files:
        return "L2"

    return "L1"


def format_agent_play_summary_ar(level: str, verification: Optional[Dict[str, Any]] = None) -> str:
    gv = verification or {}
    l4 = str(gv.get("l4_level") or gv.get("automated_l4_level") or "")
    if l4 == "L4_full":
        return "نعم — L4 كامل (حركة + قفز/نقاط — Gate مفتوح)"
    if l4 == "L4_partial":
        return "نعم — L4 جزئي (ميكانيكا أساسية — Gate مفتوح لـ C.P5)"
    labels = {
        "L5": "نعم — L5 (Gameplay مؤكد / playtest بشري)",
        "L4": "نعم — L4 (تغيير بصري بعد إدخال اللاعب)",
        "L3": "نعم — L3 (إطلاق ملف فقط — Gate محجوب)",
        "L2": "لا — L2 (ملف تنفيذي موجود — لم يُشغَّل)",
        "L1": "لا — لم يُشغَّل",
    }
    return labels.get(level, labels.get(l4, "لا"))


def build_gameplay_verification_summary(
    observation: Optional[Dict[str, Any]] = None,
    *,
    inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    gv = _gameplay_verification_blob(observation, inventory=inventory, grading_result=grading_result)
    level = resolve_gameplay_evidence_level(
        observation, inventory=inventory, grading_result=grading_result
    )
    obs = _observation_from(observation, inventory, grading_result)
    trace = _interaction_trace(obs)
    inv = inventory if isinstance(inventory, dict) else {}
    smoke = (inv.get("runtime_validation") or obs.get("runtime_validation") or {}).get(
        "functional_smoke"
    ) or {}
    gate = assess_automated_l4_gate(
        gv,
        test_document_present=_test_document_present(inv),
        functional_smoke_pass=smoke.get("functional_smoke_pass") is True,
    )
    return {
        "evidence_level": level,
        "l4_level": gv.get("l4_level") or gate.get("l4_level"),
        "agent_play_label_ar": format_agent_play_summary_ar(level, gv),
        "gameplay_agent_used": level in ("L3", "L4", "L5") or bool(gv.get("gameplay_entered")),
        "visual_delta_score": trace.get("visual_delta_score") or gv.get("visual_delta_score"),
        "runtime_verified": level in ("L4", "L5") or gate.get("l4_full") or gate.get("l4_partial"),
        "player_movement_verified": gv.get("player_movement_verified"),
        "automated_l4_gate": gate,
        "gameplay_entered": gv.get("gameplay_entered"),
    }
