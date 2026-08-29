"""Automated gameplay verification (MenuNavigator + movement) for PRO L4 without human."""
from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("ai_grader.gameplay_verifier")

VISUAL_DELTA_L4_THRESHOLD = 0.05
MOVEMENT_SHIFT_THRESHOLD = 2.5
JUMP_SHIFT_THRESHOLD = 3.0
MENU_NAV_VERSION = "menu_navigator_v2"
MOVEMENT_VERIFY_VERSION = "player_movement_verifier_v1"
AUTOMATED_GAMEPLAY_VERSION = "automated_gameplay_verification_v1"
PLAYTEST_ORCHESTRATOR_VERSION = "playtest_orchestrator_v1"

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
LOADING_VISUAL_STATES = frozenset({"loading_screen", "loading"})
SCENE_CHANGE_THRESHOLD = 0.15
PLAY_BUTTON_KEYWORDS = MENU_KEYWORDS
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
MENU_SCREEN_KEYWORDS = (
    "easy",
    "medium",
    "hard",
    "select",
    "arrow keys",
    "press enter",
    "lv-1",
    "lv-2",
)


def _enriched_observation(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Merge nested legacy/godot observation fields when top-level report is thin."""
    if not isinstance(obs, dict) or not obs:
        return {}
    merged = dict(obs)
    signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
    for key in ("legacy_observation", "godot_observation"):
        nested = signals.get(key)
        if not isinstance(nested, dict):
            continue
        if not merged.get("artifact_analyses") and nested.get("artifact_analyses"):
            merged["artifact_analyses"] = nested["artifact_analyses"]
        if not _is_nonempty_mapping(merged.get("gameplay_verification")) and _is_nonempty_mapping(
            nested.get("gameplay_verification")
        ):
            merged["gameplay_verification"] = nested["gameplay_verification"]
        if not merged.get("interaction_trace") and nested.get("interaction_trace"):
            merged["interaction_trace"] = nested["interaction_trace"]
    return merged


def _observation_from(
    observation: Optional[Dict[str, Any]],
    inventory: Optional[Dict[str, Any]],
    grading_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if isinstance(observation, dict) and observation:
        return _enriched_observation(observation)
    inv = inventory if isinstance(inventory, dict) else {}
    if isinstance(inv.get("runtime_observation_report"), dict):
        return _enriched_observation(inv["runtime_observation_report"])
    if isinstance(grading_result, dict) and isinstance(
        grading_result.get("runtime_observation_report"), dict
    ):
        return _enriched_observation(grading_result["runtime_observation_report"])
    return {}


def _is_nonempty_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _interaction_trace_from_obs(obs: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
    direct = obs.get("interaction_trace") or obs.get("runtime_interaction_trace") or {}
    if _is_nonempty_mapping(direct):
        return direct, None

    signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
    for source, nested in (
        ("signals.legacy_observation", signals.get("legacy_observation")),
        ("signals.godot_observation", signals.get("godot_observation")),
        ("legacy_observation", obs.get("legacy_observation")),
    ):
        if not isinstance(nested, dict):
            continue
        trace = nested.get("interaction_trace") or nested.get("runtime_interaction_trace")
        if _is_nonempty_mapping(trace):
            return trace, source

    for row in obs.get("interaction_trace_summary") or obs.get("artifact_analyses") or []:
        if isinstance(row, dict) and _is_nonempty_mapping(row.get("interaction_trace")):
            return row["interaction_trace"], "artifact_analyses[].interaction_trace"
        if isinstance(row, dict) and row.get("visual_delta_score") is not None:
            return row, "artifact_analyses[].visual_delta_score"
    return {}, None


def _interaction_trace(obs: Dict[str, Any]) -> Dict[str, Any]:
    trace, source = _interaction_trace_from_obs(obs)
    if source:
        logger.warning(
            "interaction_trace_fallback",
            extra={"source": source},
        )
    return trace


def _gameplay_verification_from_nested(obs: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
    signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
    for source, nested in (
        ("signals.legacy_observation", signals.get("legacy_observation")),
        ("signals.godot_observation", signals.get("godot_observation")),
        ("legacy_observation", obs.get("legacy_observation")),
    ):
        if not isinstance(nested, dict):
            continue
        gv = nested.get("gameplay_verification")
        if _is_nonempty_mapping(gv):
            return dict(gv), source

    for row in obs.get("artifact_analyses") or []:
        if not isinstance(row, dict):
            continue
        gv = row.get("gameplay_verification")
        if _is_nonempty_mapping(gv):
            return dict(gv), "artifact_analyses[].gameplay_verification"
    return {}, None


def _capture_scope_degraded(shots: Any) -> bool:
    """True when the run recorded desktop_fallback captures with NO valid
    game_window capture — the agent went blind (window closed / capture lost).

    Conservative: fires only when desktop_fallback is explicitly recorded, so
    runs whose screenshot records lack capture_scope are unaffected.
    """
    if not isinstance(shots, list) or not shots:
        return False
    saw_desktop = False
    for s in shots:
        if not isinstance(s, dict):
            continue
        scope = str(s.get("capture_scope") or "")
        if scope == "game_window" and s.get("status") == "captured":
            return False
        if scope == "desktop_fallback":
            saw_desktop = True
    return saw_desktop


def _ensure_failure_reason_code_on_negative_gameplay(
    gv: Dict[str, Any],
    obs: Dict[str, Any],
) -> Dict[str, Any]:
    """Terminal classify when gameplay failed but no failure_reason_code (blocking-bug guard)."""
    if not isinstance(gv, dict) or not gv:
        return gv
    if gv.get("gameplay_entered") is not False:
        return gv
    if gv.get("terminal_classify") == "capture_pipeline":
        return gv
    if gv.get("failure_reason_code"):
        # Consistency upgrade: a stale NO_VISUAL_RESPONSE_TO_INPUT code must not
        # survive when this run has desktop_fallback captures only — the agent
        # was blind, so blaming the game is dishonest. Keep every other code.
        if gv.get("failure_reason_code") == "NO_VISUAL_RESPONSE_TO_INPUT" and _capture_scope_degraded(
            obs.get("runtime_screenshots")
        ):
            from app.godot_runtime.failure_taxonomy import classify_capture_failure

            failure = classify_capture_failure(
                window_detected=bool(obs.get("runtime_observed")),
                process_alive=bool(obs.get("runtime_observed")),
                capture_scope_last="desktop_fallback",
                capture_retries_exhausted=True,
                probe_phase="mid_run_window_lost",
            )
            upgraded = dict(gv)
            upgraded["failure_reason_code"] = failure.code
            upgraded["failure_reason_ar"] = failure.reason_ar
            upgraded["failure_evidence"] = failure.evidence
            upgraded["terminal_classify"] = "capture_pipeline"
            return upgraded
        return gv

    trace = obs.get("interaction_trace") or obs.get("runtime_interaction_trace") or {}
    if not isinstance(trace, dict):
        trace = {}
    trace_errors = [str(e) for e in (trace.get("errors") or [])]
    if any(
        "desktop_fallback not permitted" in err or "game_window capture failed" in err
        for err in trace_errors
    ):
        from app.godot_runtime.failure_taxonomy import classify_capture_failure

        signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
        shots = obs.get("runtime_screenshots") or []
        window_detected = bool(obs.get("runtime_observed")) or any(
            isinstance(s, dict) and s.get("status") == "captured" for s in shots
        )
        failure = classify_capture_failure(
            window_detected=window_detected,
            process_alive=window_detected or signals.get("runtime_launch_attempted") is True,
            capture_scope_last="desktop_fallback",
            capture_retries_exhausted=True,
            probe_phase="tagged_capture",
        )
        enriched = dict(gv)
        enriched["failure_reason_code"] = failure.code
        enriched["failure_reason_ar"] = failure.reason_ar
        enriched["failure_evidence"] = failure.evidence
        enriched.setdefault("terminal_classify", "capture_pipeline")
        return enriched

    from app.godot_runtime.failure_taxonomy import classify_runtime_failure

    signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
    shots = obs.get("runtime_screenshots") or []
    window_detected = bool(obs.get("runtime_observed")) or any(
        isinstance(s, dict) and s.get("status") == "captured" for s in shots
    )
    proc_crashed = signals.get("crash") == "observed" or obs.get("smoke_result") in (
        "early_exit",
        "launch_error",
    )
    interaction_ran = bool(trace.get("steps") or trace.get("interaction_done"))
    failure = classify_runtime_failure(
        window_detected=window_detected,
        black_screen_duration_s=0,
        gameplay_entered=False,
        mechanics_verified_count=int(gv.get("mechanics_verified_count") or 0),
        menu_status=str(
            gv.get("menu_status")
            or ("interaction_not_reached" if not interaction_ran else "unknown")
        ),
        visual_response=bool(gv.get("visual_response")),
        server_dialog_detected=False,
        process_crashed=proc_crashed,
        boot_timed_out=not interaction_ran
        and obs.get("smoke_result") in ("stable_window", "launch_ok"),
        capture_scope_degraded=_capture_scope_degraded(shots),
    )
    if failure is None:
        return gv
    enriched = dict(gv)
    enriched["failure_reason_code"] = failure.code
    enriched["failure_reason_ar"] = failure.reason_ar
    enriched["failure_evidence"] = failure.evidence
    enriched.setdefault("terminal_classify", "consumer_ensure")
    return enriched


def _gameplay_verification_blob(
    observation: Optional[Dict[str, Any]] = None,
    *,
    inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inv = inventory if isinstance(inventory, dict) else {}
    obs = _observation_from(observation, inventory, grading_result)

    def _finalize(blob: Dict[str, Any]) -> Dict[str, Any]:
        return _ensure_failure_reason_code_on_negative_gameplay(blob, obs)

    # Preference order (authoritative-first): result -> inventory -> observation.
    # sync_authoritative_gv writes the resolved GV into result + inventory, so
    # the synced inventory must win over a raw observation blob (which may be a
    # stale weak L3 shell on pre-sync snapshots).
    if isinstance(grading_result, dict) and _is_nonempty_mapping(
        grading_result.get("gameplay_verification")
    ):
        return _finalize(dict(grading_result["gameplay_verification"]))
    if _is_nonempty_mapping(inv.get("gameplay_verification")):
        return _finalize(dict(inv["gameplay_verification"]))
    if _is_nonempty_mapping(obs.get("gameplay_verification")):
        return _finalize(dict(obs["gameplay_verification"]))

    nested_gv, source = _gameplay_verification_from_nested(obs)
    if nested_gv:
        submission_id = None
        if isinstance(grading_result, dict):
            submission_id = grading_result.get("submission_id")
        logger.warning(
            "gameplay_verification_fallback",
            extra={"source": source, "submission_id": submission_id},
        )
        nested_gv["_resolution_source"] = source
        return _finalize(nested_gv)

    trace = _interaction_trace(obs)
    if trace.get("l4_level") or trace.get("automated_l4_level"):
        trace_errors = [str(e) for e in (trace.get("errors") or [])]
        if any(
            "desktop_fallback not permitted" in err or "game_window capture failed" in err
            for err in trace_errors
        ):
            from app.godot_runtime.failure_taxonomy import classify_capture_failure

            signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
            window_detected = bool(obs.get("runtime_observed")) or signals.get(
                "runtime_launch_attempted"
            ) is True
            failure = classify_capture_failure(
                window_detected=window_detected,
                process_alive=window_detected,
                capture_scope_last="desktop_fallback",
                probe_phase="tagged_capture",
            )
            blob = dict(trace)
            blob["failure_reason_code"] = failure.code
            blob["failure_reason_ar"] = failure.reason_ar
            blob["failure_evidence"] = failure.evidence
            blob["terminal_classify"] = "capture_pipeline"
            blob["gameplay_entered"] = False
            return blob
        return _finalize(dict(trace))
    return {}


def _authoritative_gv_richness(gv: Dict[str, Any]) -> int:
    if not isinstance(gv, dict) or not gv:
        return 0
    score = 0
    code = str(gv.get("failure_reason_code") or "")
    if code == "GAME_WINDOW_CAPTURE_FAILED":
        score += 10
    elif code:
        score += 3
    if gv.get("godot_retry_attempts"):
        score += 5
    if gv.get("terminal_classify") == "capture_pipeline":
        score += 8
    if gv.get("menu_navigation"):
        score += 2
    if gv.get("evidence_package"):
        score += 2
    if gv.get("gameplay_entered") is True:
        score += 4
    elif gv.get("gameplay_entered") is False:
        score += 1
    return score


def resolve_authoritative_gameplay_verification(
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pick richest gameplay_verification from orchestrator outputs (never interaction trace)."""
    from app.runtime.orchestrator import promote_nested_runtime_observations

    inv = dict(artifact_inventory or {})
    rt = dict(inv.get("runtime_observation_report") or {})
    signals = rt.get("signals") if isinstance(rt.get("signals"), dict) else {}
    promote_nested_runtime_observations(
        rt,
        signals.get("legacy_observation"),
        signals.get("godot_observation"),
    )

    candidates: List[Dict[str, Any]] = []

    def _add(gv: Any) -> None:
        if isinstance(gv, dict) and gv:
            candidates.append(dict(gv))

    if isinstance(grading_result, dict):
        _add(grading_result.get("gameplay_verification"))
    _add(inv.get("gameplay_verification"))
    _add(rt.get("gameplay_verification"))

    def _walk(obj: Any, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(obj, dict):
            _add(obj.get("gameplay_verification"))
            # Engine adapters do not all use the same nesting shape.  Godot
            # writes under signals.godot_observation while GameMaker writes
            # platform_analyses[*].signals.gamemaker_observation.analyses[*].
            # Walk only known observation containers; deliberately never walk
            # interaction_trace because it is derived, not authoritative GV.
            for list_key in ("artifact_analyses", "analyses", "platform_analyses"):
                for row in obj.get(list_key) or []:
                    if isinstance(row, dict):
                        _walk(row, depth + 1)
            for key in (
                "legacy_observation",
                "godot_observation",
                "gamemaker_observation",
                "gamemaker_observation_summary",
                "signals",
                "normalized",
                "evidence_bundle",
                "runtime_observation_report",
            ):
                nested = obj.get(key)
                if isinstance(nested, dict):
                    _walk(nested, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:24]:
                _walk(item, depth + 1)

    _walk(rt)
    _walk(inv)
    if not candidates:
        return {}
    best = max(candidates, key=_authoritative_gv_richness)
    return dict(best)


def sync_authoritative_gv(
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> bool:
    """Write richest gameplay_verification from resolve_authoritative into result + inventory."""
    inv = artifact_inventory if isinstance(artifact_inventory, dict) else {}
    result = grading_result if isinstance(grading_result, dict) else {}
    synced = resolve_authoritative_gameplay_verification(
        artifact_inventory=inv,
        grading_result=result,
    )
    if not _is_nonempty_mapping(synced):
        return False
    gv = dict(synced)
    result["gameplay_verification"] = gv
    inv["gameplay_verification"] = gv
    rt = inv.get("runtime_observation_report")
    if isinstance(rt, dict):
        rt_out = dict(rt)
        rt_out["gameplay_verification"] = gv
        inv["runtime_observation_report"] = rt_out
    result["artifact_inventory"] = inv
    return True


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
    """Return (horizontal_shift, vertical_shift) motion evidence on center 40% band.

    FIXED 2026-07-06 (false-positive bug, submission 50 / Ahmad Bakr):
    The previous implementation returned ``max`` mean-abs-diff across artificial
    offsets. Any textured frame (HUD boxes, tiles) compared against ITSELF at a
    nonzero offset produces a large diff, so the metric measured TEXTURE, not
    MOTION — identical before/after frames scored h~7.4 / v~26.5 and always
    crossed the 2.5/3.0 thresholds, falsely "verifying" movement and jump.

    Correct semantics: motion evidence = frame difference at zero offset (d0)
    MINUS how well a translation re-aligns them (best shifted diff).
    - identical frames            -> d0 = 0                     -> 0 (no motion)
    - HUD-only change (timer)     -> d0 small, no alignment gain -> ~0
    - real translation (movement) -> d0 large, aligned offset recovers -> positive
    Honest under-detection is acceptable (L5 video path exists); false
    verification is never acceptable.
    """
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

        def _mean_abs_diff(dx: int, dy: int) -> float:
            total = 0.0
            count = 0
            for y in range(48):
                ny = y + dy
                if not (0 <= ny < 48):
                    continue
                for x in range(48):
                    nx = x + dx
                    if 0 <= nx < 48:
                        total += abs(int(b_px[y * 48 + x]) - int(a_px[ny * 48 + nx]))
                        count += 1
            return total / count if count else 0.0

        d0 = _mean_abs_diff(0, 0)
        if d0 <= 0.0:
            return 0.0, 0.0
        best_h_aligned = min(
            (_mean_abs_diff(offset, 0) for offset in range(-6, 7) if offset != 0),
            default=d0,
        )
        best_v_aligned = min(
            (_mean_abs_diff(0, offset) for offset in range(-6, 7) if offset != 0),
            default=d0,
        )
        h_score = max(0.0, d0 - best_h_aligned)
        v_score = max(0.0, d0 - best_v_aligned)
        return round(h_score, 3), round(v_score, 3)
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


def _send_key_win_legacy(vk: int, *, hold_ms: int = 80) -> bool:
    """GameMaker-compatible Windows key event path."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(max(hold_ms, 20) / 1000.0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True
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


def _key_hold_legacy(label: str, seconds: float) -> bool:
    vk_map = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "SPACE": 0x20, "ENTER": 0x0D}
    vk = vk_map.get(label.upper())
    if vk is None or sys.platform != "win32":
        return False
    try:
        import ctypes

        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(max(seconds, 0.1))
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True
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


def _shot_ocr_text(shot: Dict[str, Any]) -> str:
    if shot.get("ocr_text") is not None:
        return str(shot["ocr_text"]).lower()
    return _ocr_image_path(str(shot.get("path") or ""))


def _find_play_button_ocr(shot: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """Return image-relative (x, y) center of a play/start OCR token, if found."""
    path = str(shot.get("path") or "")
    if not path or not Path(path).is_file():
        return None
    try:
        import pytesseract  # type: ignore
        from PIL import Image

        data = pytesseract.image_to_data(
            Image.open(path).convert("RGB"),
            output_type=pytesseract.Output.DICT,
            lang="eng",
            config="--psm 6",
        )
        for idx, word in enumerate(data.get("text") or []):
            token = (word or "").strip().lower()
            if not token:
                continue
            if not any(kw in token or token in kw for kw in PLAY_BUTTON_KEYWORDS):
                continue
            left = int(data["left"][idx])
            top = int(data["top"][idx])
            width = int(data["width"][idx])
            height = int(data["height"][idx])
            if width <= 0 or height <= 0:
                continue
            return left + width // 2, top + height // 2
    except Exception:
        return None
    return None


def _looks_like_large_center_menu_button(shot: Dict[str, Any]) -> bool:
    """Detect a large bright GameMaker-style play button without OCR.

    Student games frequently render PLAY with a bitmap font that Tesseract
    cannot read.  A large, bright, saturated panel across the upper-middle of
    the client is a safer menu signal than the old coloured-HUD heuristic.
    The detector deliberately requires both coverage and a bounded vertical
    extent so ordinary green scenery does not qualify.
    """
    path = str(shot.get("path") or "")
    if not path or not Path(path).is_file():
        return False
    try:
        from PIL import Image  # type: ignore

        image = Image.open(path).convert("RGB")
        width, height = image.size
        # Exclude native title chrome and inspect the region where main-menu
        # buttons normally live.  Resize to keep the operation inexpensive.
        region = image.crop(
            (
                int(width * 0.08),
                int(height * 0.08),
                int(width * 0.92),
                int(height * 0.56),
            )
        ).resize((168, 96))
        bright_saturated = 0
        bright_green = 0
        for red, green, blue in region.getdata():
            high = max(red, green, blue)
            low = min(red, green, blue)
            if high >= 155 and high - low >= 55:
                bright_saturated += 1
            if green >= 145 and green >= red * 1.18 and green >= blue * 1.45:
                bright_green += 1
        area = max(1, region.width * region.height)
        return bright_saturated / area >= 0.19 and bright_green / area >= 0.12
    except OSError:
        return False


def _click_gamemaker_menu_candidate(
    *,
    shot: Dict[str, Any],
    attempt: int,
    process_pid: Optional[int],
    artifact_path: Path,
) -> bool:
    """Click conservative image-relative menu positions in a GameMaker client."""
    path = str(shot.get("path") or "")
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        bbox = shot.get("game_window_bbox") or (0, 0, 1, 1)
        width = max(1, int(bbox[2]) - int(bbox[0]))
        height = max(1, int(bbox[3]) - int(bbox[1]))

    # First candidate targets the common large PLAY button.  The second covers
    # centred menus without risking clicks near native window controls.
    rel_y = (0.32, 0.50)[min(attempt, 1)]
    return _click_at_image_position(
        shot=shot,
        image_xy=(width // 2, int(height * rel_y)),
        process_pid=process_pid,
        artifact_path=artifact_path,
    )


def _click_at_image_position(
    *,
    shot: Dict[str, Any],
    image_xy: Tuple[int, int],
    process_pid: Optional[int],
    artifact_path: Path,
) -> bool:
    if sys.platform != "win32":
        return False
    try:
        from app.window_focus_manager import focus_game_window, resolve_game_window_bbox

        focus_game_window(process_pid=process_pid)
        bbox = shot.get("game_window_bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            resolved = resolve_game_window_bbox(artifact_path=artifact_path, process_pid=process_pid)
            bbox = list(resolved) if resolved else None
        if not bbox:
            return False
        left, top, right, bottom = [int(v) for v in bbox]
        img_w = int(shot.get("image_width") or (right - left) or 1)
        img_h = int(shot.get("image_height") or (bottom - top) or 1)
        rel_x = max(0.0, min(1.0, image_xy[0] / max(img_w, 1)))
        rel_y = max(0.0, min(1.0, image_xy[1] / max(img_h, 1)))
        cx = left + int((right - left) * rel_x)
        cy = top + int((bottom - top) * rel_y)
        import ctypes

        ctypes.windll.user32.SetCursorPos(cx, cy)
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return True
    except Exception:
        return False


@dataclass
class MenuNavigationResult:
    status: str
    attempts: int = 0
    log: List[Dict[str, Any]] = field(default_factory=list)
    screenshot: Optional[Dict[str, Any]] = None
    entry_screenshot: Optional[Dict[str, Any]] = None
    visual_state: str = "unknown"
    gameplay_entered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": MENU_NAV_VERSION,
            "status": self.status,
            "attempts": self.attempts,
            "log": self.log,
            "screenshot": self.screenshot,
            "entry_screenshot": self.entry_screenshot or self.screenshot,
            "visual_state": self.visual_state,
            "gameplay_entered": self.gameplay_entered,
        }


class MenuNavigator:
    """Detect menu screens and attempt to enter gameplay."""

    MAX_ATTEMPTS = 8
    GODOT_BOOT_WAIT = 6.0
    BOOT_POLL_INTERVAL = 1.5
    BOOT_POLL_MAX = 10
    BLACK_SCREEN_THRESHOLD = 0.05
    SCENE_CHANGE_THRESHOLD = SCENE_CHANGE_THRESHOLD

    def __init__(self, *, max_attempts: int = MAX_ATTEMPTS) -> None:
        self.max_attempts = max(1, min(max_attempts, self.MAX_ATTEMPTS))

    @staticmethod
    def _is_gamemaker_export(artifact_path: Path) -> bool:
        """GameMaker runners have their data.win beside the executable."""
        return (artifact_path.parent / "data.win").is_file()

    def _is_black_screen(self, shot: Dict[str, Any]) -> bool:
        """True when the capture is mostly black (Godot splash / still loading)."""
        state = str(shot.get("visual_state") or "").lower()
        if state == "black_screen":
            return True
        stats = shot.get("visual_stats") or {}
        if stats.get("black_screen_possible") is True:
            return True
        avg_luma = stats.get("avg_luma_approx")
        if avg_luma is not None:
            try:
                if float(avg_luma) < 12.0:
                    return True
            except (TypeError, ValueError):
                pass
        path = str(shot.get("path") or "")
        if not path or not Path(path).is_file():
            return False
        try:
            from PIL import Image  # type: ignore

            pixels = list(Image.open(path).convert("L").getdata())
            if not pixels:
                return True
            bright = sum(1 for p in pixels if int(p) > 30)
            return (bright / len(pixels)) < self.BLACK_SCREEN_THRESHOLD
        except Exception:
            return False

    @staticmethod
    def _is_strict_game_window_capture(shot: Dict[str, Any]) -> bool:
        """True only for a capture cropped from the launched game window."""
        if not isinstance(shot, dict) or shot.get("status") != "captured":
            return False
        if str(shot.get("capture_scope") or "").lower() != "game_window":
            return False
        return bool(shot.get("game_window_detected") or shot.get("game_window_bbox"))

    @classmethod
    def _same_game_window_capture(
        cls,
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> bool:
        """Reject desktop-to-window transitions as gameplay scene changes."""
        if not cls._is_strict_game_window_capture(before):
            return False
        if not cls._is_strict_game_window_capture(after):
            return False
        before_pid = before.get("process_pid")
        after_pid = after.get("process_pid")
        if before_pid is not None and after_pid is not None and before_pid != after_pid:
            return False
        return True

    def _wait_for_boot_screen_clear(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        from app.window_focus_manager import focus_game_window

        last_shot: Dict[str, Any] = {}
        is_gamemaker = self._is_gamemaker_export(artifact_path)
        for boot_attempt in range(self.BOOT_POLL_MAX):
            focus_game_window(process_pid=process_pid)
            if boot_attempt == 0:
                # GameMaker exports are already windowed shortly after launch.
                # Waiting the Godot boot interval here delayed input until the
                # game window had been lost in short smoke sessions.
                time.sleep(1.0 if self._is_gamemaker_export(artifact_path) else self.GODOT_BOOT_WAIT)
            else:
                time.sleep(self.BOOT_POLL_INTERVAL)
            shot = capture_screenshot(
                artifact_path,
                label=f"boot_wait_{boot_attempt}",
                elapsed_seconds=elapsed_seconds + boot_attempt * self.BOOT_POLL_INTERVAL,
                process_pid=process_pid,
            )
            last_shot = shot if isinstance(shot, dict) else {}
            # A desktop fallback can be the grading page behind a game that has
            # not created its window yet.  It is not a GameMaker boot/menu frame.
            if is_gamemaker and not self._is_strict_game_window_capture(last_shot):
                continue
            if not self._is_black_screen(last_shot):
                return last_shot
        return last_shot

    def classify_visual_state(self, shot: Dict[str, Any]) -> str:
        """Return: gameplay | menu | loading | unknown."""
        if self._is_black_screen(shot):
            return "loading"
        state = str(shot.get("visual_state") or "").lower()
        ocr = _shot_ocr_text(shot)
        if state in LOADING_VISUAL_STATES:
            return "loading"
        has_hud = _hud_keywords_in_text(ocr)
        has_menu = _menu_keywords_in_text(ocr)
        has_menu_screen = any(keyword in ocr for keyword in MENU_SCREEN_KEYWORDS)
        has_large_menu_button = _looks_like_large_center_menu_button(shot)
        # The screenshot heuristic calls visually rich frames "gameplay_candidate".
        # A GameMaker title screen with colourful level buttons is rich too, so do
        # not treat that hint as proof of gameplay unless the HUD is visible.
        if state == "gameplay_candidate":
            if has_large_menu_button:
                return "menu"
            if has_hud:
                return "gameplay"
            if _looks_like_gamemaker_hud(shot):
                return "gameplay"
            if has_menu or has_menu_screen:
                return "menu"
            return "unknown"
        if has_hud and not has_menu:
            return "gameplay"
        if state in MENU_VISUAL_STATES or has_menu or has_menu_screen:
            return "menu"
        return "unknown"

    def _dismiss_menu(
        self,
        *,
        shot: Dict[str, Any],
        attempt: int,
        artifact_path: Path,
        process_pid: Optional[int],
    ) -> str:
        if self._is_gamemaker_export(artifact_path):
            play_pos = _find_play_button_ocr(shot)
            if play_pos and _click_at_image_position(
                shot=shot,
                image_xy=play_pos,
                process_pid=process_pid,
                artifact_path=artifact_path,
            ):
                return "gamemaker_click_play_ocr"
            # Mouse-event buttons are common in student GameMaker projects.
            # Try visible central button locations before the keyboard fallback.
            if attempt < 2 and _looks_like_large_center_menu_button(shot) and _click_gamemaker_menu_candidate(
                shot=shot,
                attempt=attempt,
                process_pid=process_pid,
                artifact_path=artifact_path,
            ):
                return "gamemaker_click_menu_candidate"
            # Keyboard-driven menus still receive an explicit selection event.
            _send_key_win_legacy(0x28)  # Down arrow
            time.sleep(0.30)
            _send_key_win_legacy(0x0D)  # Enter
            return "gamemaker_arrow_select_enter"
        play_pos = _find_play_button_ocr(shot)
        if play_pos and _click_at_image_position(
            shot=shot,
            image_xy=play_pos,
            process_pid=process_pid,
            artifact_path=artifact_path,
        ):
            return "click_play_ocr"
        _click_game_window_center(process_pid=process_pid, artifact_path=artifact_path)
        if attempt % 2 == 0:
            _send_key_win(0x0D)
        else:
            _send_key_win(0x20)
        return "menu_dismiss_keys"

    def navigate_to_gameplay(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
    ) -> MenuNavigationResult:
        from app.window_focus_manager import focus_game_window

        log: List[Dict[str, Any]] = []
        last_shot: Optional[Dict[str, Any]] = None
        action_baseline: Optional[Dict[str, Any]] = None
        last_state = "unknown"

        boot_shot = self._wait_for_boot_screen_clear(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            elapsed_seconds=elapsed_seconds,
        )
        if boot_shot:
            last_shot = boot_shot
            boot_state = self.classify_visual_state(boot_shot)
            if boot_state == "gameplay":
                return MenuNavigationResult(
                    status="gameplay_entered",
                    attempts=0,
                    log=[{"attempt": -1, "action": "boot_wait", "visual_state": boot_state}],
                    screenshot=boot_shot,
                    entry_screenshot=boot_shot,
                    visual_state=boot_state,
                    gameplay_entered=True,
                )
            last_state = boot_state

        attempt_limit = min(self.max_attempts, 3) if self._is_gamemaker_export(artifact_path) else self.max_attempts
        for attempt in range(attempt_limit):
            focus_game_window(process_pid=process_pid)
            time.sleep(0.35)
            shot = capture_screenshot(
                artifact_path,
                label=f"menu_nav_{attempt}",
                elapsed_seconds=elapsed_seconds + attempt * 0.5,
                process_pid=process_pid,
            )
            last_shot = shot
            visual_state = self.classify_visual_state(shot)
            last_state = visual_state

            if self._is_gamemaker_export(artifact_path) and not self._is_strict_game_window_capture(shot):
                log.append(
                    {
                        "attempt": attempt,
                        "action": "wait_game_window",
                        "visual_state": visual_state,
                        "capture_scope": shot.get("capture_scope"),
                    }
                )
                action_baseline = None
                time.sleep(1.0)
                continue

            if (
                action_baseline is not None
                and self._is_gamemaker_export(artifact_path)
                and self._same_game_window_capture(action_baseline, shot)
            ):
                changed, delta, detail = RequirementVerifier().verify_scene_change(
                    action_baseline,
                    shot,
                    self.SCENE_CHANGE_THRESHOLD,
                )
                if changed:
                    log.append(
                        {
                            "attempt": attempt,
                            "action": "scene_change_confirmed",
                            "visual_state": visual_state,
                            "detail": detail,
                            "confidence": delta,
                        }
                    )
                    return MenuNavigationResult(
                        status="gameplay_entered",
                        attempts=attempt + 1,
                        log=log,
                        screenshot=shot,
                        entry_screenshot=shot,
                        visual_state="gameplay",
                        gameplay_entered=True,
                    )

            if visual_state == "gameplay":
                return MenuNavigationResult(
                    status="gameplay_entered",
                    attempts=attempt + 1,
                    log=log,
                    screenshot=shot,
                    entry_screenshot=shot,
                    visual_state=visual_state,
                    gameplay_entered=True,
                )

            if visual_state == "loading":
                log.append({"attempt": attempt, "action": "wait_loading", "visual_state": visual_state})
                time.sleep(2.0)
                continue

            action = self._dismiss_menu(
                shot=shot,
                attempt=attempt,
                artifact_path=artifact_path,
                process_pid=process_pid,
            )
            log.append({"attempt": attempt, "action": action, "visual_state": visual_state})
            action_baseline = shot
            time.sleep(3.2 if self._is_gamemaker_export(artifact_path) else 2.0)

        status = "stuck_in_menu" if last_state == "menu" else "unknown"
        if last_state == "loading" or (
            last_shot and self._is_black_screen(last_shot)
        ):
            status = "black_screen"
        return MenuNavigationResult(
            status=status,
            attempts=attempt_limit,
            log=log,
            screenshot=last_shot,
            visual_state=last_state,
            gameplay_entered=False,
        )

    def detect_and_enter_gameplay(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        """Backward-compatible dict result for runtime_observation_sandbox."""
        return self.navigate_to_gameplay(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            elapsed_seconds=elapsed_seconds,
        ).to_dict()


class EvidenceQualityError(RuntimeError):
    """Raised when PRO mode cannot accept a screenshot as gameplay evidence."""


class CaptureFailureError(EvidenceQualityError):
    """PRO game_window capture failed after retries."""

    def __init__(
        self,
        message: str,
        *,
        requirement_id: str = "",
        phase: str = "",
        capture_scope_last: str = "",
        probe_phase: str = "tagged_capture",
    ) -> None:
        super().__init__(message)
        self.requirement_id = requirement_id
        self.phase = phase
        self.capture_scope_last = capture_scope_last
        self.probe_phase = probe_phase


def build_capture_failure_gv(
    exc: CaptureFailureError,
    *,
    process_pid: Optional[int] = None,
) -> Dict[str, Any]:
    from app.godot_runtime.failure_taxonomy import classify_capture_failure

    failure = classify_capture_failure(
        window_detected=process_pid is not None,
        process_alive=process_pid is not None,
        capture_scope_last=exc.capture_scope_last,
        capture_retries_exhausted=True,
        probe_phase=exc.probe_phase,
        requirement_id=exc.requirement_id,
        phase=exc.phase,
    )
    return {
        "mode": AUTOMATED_GAMEPLAY_VERSION,
        "gameplay_entered": False,
        "failure_reason_code": failure.code,
        "failure_reason_ar": failure.reason_ar,
        "failure_evidence": failure.evidence,
        "terminal_classify": "capture_pipeline",
        "l4_level": "L3",
        "automated_l4_level": "L3",
    }


@dataclass
class RequirementResult:
    req_id: str
    verified: bool
    confidence: float = 0.0
    reason: str = ""
    btec_criteria: List[str] = field(default_factory=list)
    before_screenshot: Optional[Dict[str, Any]] = None
    after_screenshot: Optional[Dict[str, Any]] = None
    detail: str = ""
    verification_basis: str = "direct_runtime_test"
    evidence_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.req_id,
            "verified": self.verified,
            "confidence": self.confidence,
            "reason": self.reason,
            "btec_criteria": list(self.btec_criteria),
            "detail": self.detail,
            "verification_basis": self.verification_basis,
            "evidence_sources": list(self.evidence_sources),
            "before_screenshot": self.before_screenshot,
            "after_screenshot": self.after_screenshot,
        }


@dataclass
class EvidencePackage:
    submission_id: str = ""
    results: List[RequirementResult] = field(default_factory=list)
    gameplay_entered: bool = False
    screenshots: List[Dict[str, Any]] = field(default_factory=list)
    version: str = PLAYTEST_ORCHESTRATOR_VERSION

    def get_result(self, req_id: str) -> Optional[RequirementResult]:
        for row in self.results:
            if row.req_id == req_id:
                return row
        return None

    def verified_mechanic_ids(self) -> List[str]:
        mechanics = (
            "player_movement",
            "player_jump",
            "score_system",
            "collect_items",
            "lives_system",
            "enemy_interaction",
            "win_lose_condition",
        )
        return [m for m in mechanics if (r := self.get_result(m)) and r.verified]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "submission_id": self.submission_id,
            "gameplay_entered": self.gameplay_entered,
            "results": [r.to_dict() for r in self.results],
            "screenshots": self.screenshots,
            "mechanics_verified_count": len(self.verified_mechanic_ids()),
        }

    def to_movement_verification_dict(self) -> Dict[str, Any]:
        movement = self.get_result("player_movement")
        jump = self.get_result("player_jump")
        score = self.get_result("score_system")
        movement_ok = bool(self.gameplay_entered and movement and movement.verified)
        jump_ok = bool(self.gameplay_entered and jump and jump.verified)
        score_ok = bool(self.gameplay_entered and score and score.verified)
        mechanics = len(self.verified_mechanic_ids())
        l4_level = calculate_l4_level(
            gameplay_entered=self.gameplay_entered,
            mechanics_verified_count=mechanics,
        )
        shots = []
        for row in self.results:
            if row.before_screenshot:
                shots.append(row.before_screenshot)
            if row.after_screenshot:
                shots.append(row.after_screenshot)
        h_shift = 0.0
        v_shift = 0.0
        if movement and movement.detail.startswith("h_shift="):
            try:
                h_shift = float(movement.detail.split("=", 1)[1])
            except ValueError:
                h_shift = 0.0
        if jump and jump.detail.startswith("v_shift="):
            try:
                v_shift = float(jump.detail.split("=", 1)[1])
            except ValueError:
                v_shift = 0.0
        return {
            "version": MOVEMENT_VERIFY_VERSION,
            "movement": movement_ok,
            "jump": jump_ok,
            "score_change": score_ok,
            "horizontal_shift": h_shift,
            "vertical_shift": v_shift,
            "mechanics_verified_count": mechanics,
            "l4_level": l4_level,
            "automated_l4_level": l4_level,
            "player_movement_verified": movement_ok,
            "jump_detected": jump_ok,
            "score_change_detected": score_ok,
            "screenshots": shots,
            "requirement_results": [r.to_dict() for r in self.results],
        }


def _execute_input_action(
    action: Any,
    *,
    artifact_path: Path,
    process_pid: Optional[int],
) -> str:
    from app.requirement_extractor import InputAction

    if not isinstance(action, InputAction):
        return "skipped"
    if action.action == "click_center":
        _click_game_window_center(process_pid=process_pid, artifact_path=artifact_path)
        return "click_center"
    if action.action == "key":
        key = (action.key or "Return").upper()
        vk_map = {"RETURN": 0x0D, "ENTER": 0x0D, "SPACE": 0x20}
        vk = vk_map.get(key, 0x0D)
        if (artifact_path.parent / "data.win").is_file():
            _send_key_win_legacy(vk)
        else:
            _send_key_win(vk)
        return f"key:{key}"
    if action.action == "key_hold":
        label = (action.key or "D").upper()
        if (artifact_path.parent / "data.win").is_file():
            _key_hold_legacy(label, max(action.duration, 0.1))
        else:
            _key_hold(label, max(action.duration, 0.1))
        return f"key_hold:{label}"
    if action.action == "wait":
        time.sleep(max(action.duration, 0.1))
        return f"wait:{max(action.duration, 0.1):.1f}s"
    return "unknown"


def _hud_ocr_text(shot: Dict[str, Any]) -> str:
    path = str(shot.get("path") or "")
    if not path or not Path(path).is_file():
        return _shot_ocr_text(shot)
    try:
        from PIL import Image  # type: ignore

        img = Image.open(path).convert("RGB")
        w, h = img.size
        hud = img.crop((0, 0, w, max(1, int(h * 0.15))))
        tmp = path + ".hud.png"
        hud.save(tmp)
        text = _ocr_image_path(tmp)
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
        return text
    except Exception:
        return _shot_ocr_text(shot)


def _extract_numbers(text: str) -> Tuple[int, ...]:
    import re

    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums)


def _image_region_delta(
    before: Dict[str, Any],
    after: Dict[str, Any],
    box: Tuple[float, float, float, float],
) -> float:
    """Mean normalized pixel delta inside a fractional screenshot region."""
    try:
        from PIL import Image, ImageChops, ImageStat  # type: ignore

        b = Image.open(str(before.get("path") or "")).convert("RGB")
        a = Image.open(str(after.get("path") or "")).convert("RGB")
        if b.size != a.size:
            a = a.resize(b.size)
        width, height = b.size
        px_box = (
            int(width * box[0]),
            int(height * box[1]),
            max(1, int(width * box[2])),
            max(1, int(height * box[3])),
        )
        diff = ImageChops.difference(b.crop(px_box), a.crop(px_box))
        means = ImageStat.Stat(diff).mean
        return sum(float(value) for value in means) / (len(means) * 255.0)
    except Exception:
        return 0.0


def _image_region_changed_ratio(
    before: Dict[str, Any],
    after: Dict[str, Any],
    box: Tuple[float, float, float, float],
    *,
    noise_floor: int = 8,
) -> float:
    """Fraction of region pixels with a material luma change."""
    try:
        from PIL import Image, ImageChops  # type: ignore

        b = Image.open(str(before.get("path") or "")).convert("L")
        a = Image.open(str(after.get("path") or "")).convert("L")
        if b.size != a.size:
            a = a.resize(b.size)
        width, height = b.size
        px_box = (
            int(width * box[0]),
            int(height * box[1]),
            max(1, int(width * box[2])),
            max(1, int(height * box[3])),
        )
        histogram = ImageChops.difference(b.crop(px_box), a.crop(px_box)).histogram()
        pixel_count = max(1, sum(histogram))
        return sum(histogram[max(0, noise_floor + 1) :]) / pixel_count
    except Exception:
        return 0.0


def _looks_like_gamemaker_hud(shot: Dict[str, Any]) -> bool:
    """Detect a coloured top HUD when GameMaker's bitmap font defeats OCR."""
    path = str(shot.get("path") or "")
    if not path or not Path(path).is_file():
        return False
    try:
        from PIL import Image  # type: ignore

        image = Image.open(path).convert("RGB")
        width, height = image.size
        # PrintWindow includes the native title bar.  Exclude that chrome: its
        # white controls plus a yellow game title below it made menu screens
        # look like a red/yellow/white HUD.  The real GameMaker HUD starts just
        # below the chrome and remains inside the next ~14% of the frame.
        hud_top = max(0, int(height * 0.07))
        hud_bottom = max(hud_top + 1, int(height * 0.20))
        hud = image.crop((0, hud_top, width, hud_bottom))
        red = yellow = bright = 0
        for r, g, b in hud.getdata():
            if r >= 170 and g <= 105 and b <= 105:
                red += 1
            if r >= 145 and g >= 105 and b <= 105:
                yellow += 1
            if r >= 175 and g >= 175 and b >= 175:
                bright += 1
        area = max(1, hud.width * hud.height)
        coloured_hud = red >= max(18, int(area * 0.0002)) and yellow >= max(18, int(area * 0.0002))
        text_heavy_hud = yellow >= max(80, int(area * 0.001)) and bright >= max(35, int(area * 0.0004))
        return coloured_hud or text_heavy_hud
    except Exception:
        return False


class RequirementVerifier:
    """Verify individual requirement tests from before/after screenshots."""

    def _horizontal_centroid_shift(self, before: Dict[str, Any], after: Dict[str, Any]) -> float:
        h, _ = _center_band_shift(str(before.get("path") or ""), str(after.get("path") or ""))
        return h

    def _vertical_centroid_shift(self, before: Dict[str, Any], after: Dict[str, Any]) -> float:
        _, v = _center_band_shift(str(before.get("path") or ""), str(after.get("path") or ""))
        return v

    def verify_pixel_shift_horizontal(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        if not gameplay_entered:
            return False, 0.0, "gameplay_not_entered"
        shift = self._horizontal_centroid_shift(before, after)
        conf = min(shift / max(threshold, 1e-6), 1.0)
        return shift > threshold, conf, f"h_shift={shift:.3f}"

    def verify_pixel_shift_vertical(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        if not gameplay_entered:
            return False, 0.0, "gameplay_not_entered"
        shift = self._vertical_centroid_shift(before, after)
        conf = min(shift / max(threshold, 1e-6), 1.0)
        return shift > threshold, conf, f"v_shift={shift:.3f}"

    def verify_visual_player_movement(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        """Verify top-down input response where the world itself stays static.

        The scrolling-world centroid metric is inappropriate for GameMaker
        top-down rooms: the player sprite moves locally while the tiled maze
        remains fixed.  Measure material pixel changes in the playfield and
        exclude native chrome/HUD, after a single directional input.
        """
        if not gameplay_entered:
            return False, 0.0, "gameplay_not_entered"
        h_shift = self._horizontal_centroid_shift(before, after)
        changed = _image_region_changed_ratio(
            before,
            after,
            (0.02, 0.14, 0.98, 0.96),
        )
        verified = h_shift > MOVEMENT_SHIFT_THRESHOLD or changed >= threshold
        confidence = min(
            max(
                h_shift / max(MOVEMENT_SHIFT_THRESHOLD, 1e-6),
                changed / max(threshold, 1e-6),
            ),
            1.0,
        )
        return (
            verified,
            confidence,
            f"h_shift={h_shift:.3f};playfield_changed_ratio={changed:.3f}",
        )

    def verify_ocr_hud_change(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        if not gameplay_entered:
            return False, 0.0, "gameplay_not_entered"
        nums_b = _extract_numbers(_hud_ocr_text(before))
        nums_a = _extract_numbers(_hud_ocr_text(after))
        changed = bool(nums_a) and nums_b != nums_a
        conf = threshold if changed else 0.0
        return changed, conf, f"hud={nums_b}→{nums_a}"

    def _verify_hud_region(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        box: Tuple[float, float, float, float],
        label: str,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        if not gameplay_entered:
            return False, 0.0, "gameplay_not_entered"
        delta = _image_region_delta(before, after, box)
        verified = delta >= 0.002
        return verified, min(delta / 0.015, 1.0), f"{label}_region_delta={delta:.4f}"

    def verify_score_region_change(
        self, before: Dict[str, Any], after: Dict[str, Any], threshold: float, *, gameplay_entered: bool = True
    ) -> Tuple[bool, float, str]:
        _ = threshold
        return self._verify_hud_region(before, after, (0.15, 0.0, 0.39, 0.16), "score", gameplay_entered=gameplay_entered)

    def verify_collect_region_change(
        self, before: Dict[str, Any], after: Dict[str, Any], threshold: float, *, gameplay_entered: bool = True
    ) -> Tuple[bool, float, str]:
        _ = threshold
        return self._verify_hud_region(before, after, (0.36, 0.0, 0.61, 0.16), "collect", gameplay_entered=gameplay_entered)

    def verify_lives_region_change(
        self, before: Dict[str, Any], after: Dict[str, Any], threshold: float, *, gameplay_entered: bool = True
    ) -> Tuple[bool, float, str]:
        _ = threshold
        return self._verify_hud_region(before, after, (0.0, 0.0, 0.16, 0.16), "lives", gameplay_entered=gameplay_entered)

    def verify_timer_region_change(
        self, before: Dict[str, Any], after: Dict[str, Any], threshold: float, *, gameplay_entered: bool = True
    ) -> Tuple[bool, float, str]:
        _ = threshold
        return self._verify_hud_region(before, after, (0.80, 0.0, 1.0, 0.16), "timer", gameplay_entered=gameplay_entered)

    def verify_level_region_change(
        self, before: Dict[str, Any], after: Dict[str, Any], threshold: float, *, gameplay_entered: bool = True
    ) -> Tuple[bool, float, str]:
        _ = threshold
        return self._verify_hud_region(before, after, (0.60, 0.0, 0.80, 0.16), "level", gameplay_entered=gameplay_entered)

    def verify_ocr_endgame_screen(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        if not gameplay_entered:
            return False, 0.0, "gameplay_not_entered"
        text = _shot_ocr_text(after)
        markers = ("win", "victory", "game over", "lose", "فوز", "خسارة", "حاول")
        found = any(m in text for m in markers)
        if found:
            return True, threshold, "endgame_text=True"
        changed, delta, detail = self.verify_scene_change(
            before, after, max(0.08, threshold / 4), gameplay_entered=gameplay_entered
        )
        return changed, delta, f"endgame_text=False;{detail}"

    def verify_scene_change(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        _ = gameplay_entered
        try:
            from PIL import Image  # type: ignore
            from skimage.metrics import structural_similarity as ssim  # type: ignore
            import numpy as np

            b_img = Image.open(str(before.get("path") or "")).convert("L")
            a_img = Image.open(str(after.get("path") or "")).convert("L")
            if b_img.size != a_img.size:
                a_img = a_img.resize(b_img.size)
            b = np.array(b_img)
            a = np.array(a_img)
            score, _ = ssim(b, a, full=True)
            delta = 1.0 - float(score)
            return delta > threshold, delta, f"ssim_delta={delta:.3f}"
        except Exception:
            # ``scikit-image`` is optional in the production environment.  The
            # former fallback measured only centroid movement in the middle of
            # the frame, so a genuine GameMaker menu -> maze transition could
            # still report an exact zero.  Use a dependency-free changed-pixel
            # ratio instead.  Ignoring tiny (<= 8/255) luma differences keeps
            # cursor animation and capture noise from becoming scene changes.
            try:
                from PIL import Image, ImageChops  # type: ignore

                b_img = Image.open(str(before.get("path") or "")).convert("L")
                a_img = Image.open(str(after.get("path") or "")).convert("L")
                if b_img.size != a_img.size:
                    a_img = a_img.resize(b_img.size)
                histogram = ImageChops.difference(b_img, a_img).histogram()
                pixel_count = max(1, sum(histogram))
                delta = sum(histogram[9:]) / pixel_count
                return delta > threshold, delta, f"pillow_changed_ratio={delta:.3f}"
            except Exception:
                h = self._horizontal_centroid_shift(before, after)
                v = self._vertical_centroid_shift(before, after)
                delta = max(h, v) / 100.0
                return delta > threshold, delta, f"centroid_fallback_delta={delta:.3f}"

    def verify(
        self,
        method: str,
        before: Dict[str, Any],
        after: Dict[str, Any],
        threshold: float,
        *,
        gameplay_entered: bool = True,
    ) -> Tuple[bool, float, str]:
        dispatch = {
            "pixel_shift_horizontal": self.verify_pixel_shift_horizontal,
            "pixel_shift_vertical": self.verify_pixel_shift_vertical,
            "visual_player_movement": self.verify_visual_player_movement,
            "ocr_hud_change": self.verify_ocr_hud_change,
            "visual_score_change": self.verify_score_region_change,
            "visual_collect_change": self.verify_collect_region_change,
            "visual_lives_change": self.verify_lives_region_change,
            "visual_timer_change": self.verify_timer_region_change,
            "visual_level_change": self.verify_level_region_change,
            "ocr_endgame_screen": self.verify_ocr_endgame_screen,
            "scene_change": self.verify_scene_change,
        }
        fn = dispatch.get(method)
        if fn is None:
            return False, 0.0, f"unsupported_method:{method}"
        return fn(before, after, threshold, gameplay_entered=gameplay_entered)


class PlaytestOrchestrator:
    """Run RequirementPlan against a live game window."""

    def __init__(
        self,
        *,
        pro_mode: bool = True,
        verifier: Optional[RequirementVerifier] = None,
    ) -> None:
        self.pro_mode = pro_mode
        self.verifier = verifier or RequirementVerifier()
        self.gameplay_entered = False

    def _capture_tagged(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        req_id: str,
        phase: str,
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        from app.godot_runtime.retry_policy import CAPTURE_RETRY_INTERVAL_S, CAPTURE_TAGGED_MAX_ATTEMPTS

        last_shot: Dict[str, Any] = {}
        for attempt in range(CAPTURE_TAGGED_MAX_ATTEMPTS):
            last_shot = dict(
                capture_screenshot(
                    artifact_path,
                    label=f"req_{req_id}_{phase}",
                    elapsed_seconds=elapsed_seconds,
                    process_pid=process_pid,
                    requirement_id=req_id,
                    phase=phase,
                )
                or {}
            )
            last_shot["requirement_id"] = req_id
            last_shot["phase"] = phase
            scope = str(last_shot.get("capture_scope") or "game_window")
            last_shot["capture_scope"] = scope
            if not self.pro_mode or scope == "game_window":
                return last_shot
            if attempt + 1 < CAPTURE_TAGGED_MAX_ATTEMPTS:
                try:
                    from app.window_focus_manager import focus_game_window

                    focus_game_window(process_pid=process_pid)
                except Exception:
                    pass
                time.sleep(CAPTURE_RETRY_INTERVAL_S)

        raise CaptureFailureError(
            f"game_window capture failed for {req_id}/{phase} — "
            "desktop_fallback not permitted in PRO mode",
            requirement_id=req_id,
            phase=phase,
            capture_scope_last=str(last_shot.get("capture_scope") or "desktop_fallback"),
            probe_phase="tagged_capture",
        )

    def _test_requirement(
        self,
        req: Any,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        elapsed_seconds: float,
    ) -> RequirementResult:
        from app.requirement_extractor import RequirementTest

        if not isinstance(req, RequirementTest):
            return RequirementResult(req_id="unknown", verified=False, reason="invalid_requirement")

        before = self._capture_tagged(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            req_id=req.req_id,
            phase="before",
            elapsed_seconds=elapsed_seconds,
        )
        for action in req.input_sequence:
            _execute_input_action(action, artifact_path=artifact_path, process_pid=process_pid)
            time.sleep(0.15)
        after = self._capture_tagged(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            req_id=req.req_id,
            phase="after",
            elapsed_seconds=elapsed_seconds + 0.5,
        )
        verified, confidence, detail = self.verifier.verify(
            req.verification_method,
            before,
            after,
            req.success_threshold,
            gameplay_entered=self.gameplay_entered or req.req_id == "menu_navigation",
        )
        return RequirementResult(
            req_id=req.req_id,
            verified=verified,
            confidence=confidence,
            reason="" if verified else detail,
            btec_criteria=list(req.btec_criteria),
            before_screenshot=before,
            after_screenshot=after,
            detail=detail,
        )

    def _package_from_results(
        self,
        *,
        submission_id: str,
        gameplay_entered: bool,
        results: List[RequirementResult],
        screenshots: Optional[List[Dict[str, Any]]] = None,
    ) -> EvidencePackage:
        return EvidencePackage(
            submission_id=submission_id,
            results=results,
            gameplay_entered=gameplay_entered,
            screenshots=screenshots or [],
        )

    @staticmethod
    def _submission_source_root(artifact_path: Path) -> Path:
        """Resolve the student subtree without ever scanning the application root."""
        resolved = artifact_path.resolve()
        # Source-only GameMaker projects are copied beside the isolated build
        # directory: <session>/source_project and <session>/ide_compile/runtime.
        # The old fallback returned the EXE directory, so no GML was inspected.
        for parent in list(resolved.parents)[:6]:
            candidate = parent / "source_project"
            if candidate.is_dir() and (
                any(candidate.glob("*.yyp")) or next(candidate.rglob("*.gml"), None)
            ):
                return candidate

        parts = resolved.parts
        lowered = [part.lower() for part in parts]
        if "students" in lowered:
            idx = lowered.index("students")
            # uploads/students/<batch-group>/<student>/...
            if len(parts) > idx + 2:
                return Path(*parts[: idx + 3])
        return artifact_path.parent

    @classmethod
    def _source_feature_signals(cls, artifact_path: Path) -> Dict[str, bool]:
        root = cls._submission_source_root(artifact_path)
        chunks: List[str] = []
        source_files: List[Tuple[Path, str]] = []
        total = 0
        try:
            for fp in root.rglob("*.gml"):
                if len(chunks) >= 128 or total >= 1_000_000:
                    break
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")[:80_000]
                except OSError:
                    continue
                lowered = text.lower()
                chunks.append(lowered)
                source_files.append((fp, lowered))
                total += len(text)
        except OSError:
            pass
        source = "\n".join(chunks)
        score_mutation = bool(
            re.search(
                r"\bglobal\.score\s*(?:\+=|-=|\+\+|--|=\s*global\.score\s*[+-])",
                source,
            )
        )
        collect_mutation = bool(
            re.search(
                r"\bglobal\.cheese_collected\s*(?:\+=|\+\+|=\s*global\.cheese_collected\s*\+)",
                source,
            )
        )
        collect_trigger = "obj_cheese" in source and any(
            token in source
            for token in ("instance_place(", "place_meeting(", "collision_", "instance_destroy(")
        )
        # Generic GameMaker projects rarely use canonical object/variable
        # names.  Identify the controllable object from keyboard event files,
        # then inspect only its collision handlers to avoid counting unrelated
        # decoration or dead helper objects as implemented mechanics.
        player_objects = {
            fp.parent.name.lower()
            for fp, text in source_files
            if fp.name.lower().startswith("keyboard_")
            and re.search(r"\b[xy]\s*(?:\+=|-=|=\s*[xy]\s*[+-])", text)
        }
        player_collisions = [
            text
            for fp, text in source_files
            if fp.parent.name.lower() in player_objects
            and fp.name.lower().startswith("collision_")
        ]
        generic_collect = any(
            re.search(r"\binstance_destroy\s*\(\s*other\s*\)", text)
            for text in player_collisions
        )
        generic_hazard_transition = any(
            re.search(
                r"\b(?:room_goto|game_end)\s*\(|"
                r"\b(?:global\.)?(?:lives?|mylives|health)\s*(?:-=|--|=\s*[^;\n]*-)",
                text,
            )
            for text in player_collisions
        )
        lives_mutation = bool(
            re.search(
                r"\bglobal\.lives\s*(?:-=|--|=\s*global\.lives\s*-)",
                source,
            )
        )
        timer_mutation = bool(
            re.search(
                r"\bglobal\.time_left\s*(?:-=|--|=\s*global\.time_left\s*-)",
                source,
            )
        )
        win_transition = bool(
            re.search(r"\bglobal\.phase\s*=\s*['\"]win['\"]", source)
        )
        lose_transition = bool(
            re.search(r"\bglobal\.phase\s*=\s*['\"]gameover['\"]", source)
        )
        restart_input = bool(
            re.search(
                r"keyboard_(?:check|check_pressed|key_press)[^\n]*(?:vk_enter|vk_return)",
                source,
            )
        )
        direct_restart_action = any(
            token in source
            for token in ("room_restart(", "game_restart(", 'global.phase = "playing"', "global.phase='playing'")
        )
        start_game_reset = bool(
            re.search(r"\bstart_game\s*=\s*function\s*\(", source)
            and re.search(r"\bstart_game\s*\(", source)
            and re.search(r"\bglobal\.score\s*=\s*0", source)
            and re.search(r"\bglobal\.cheese_collected\s*=\s*0", source)
            and re.search(r"\bglobal\.(?:lives|time_left)\s*=", source)
            and re.search(r"\bglobal\.phase\s*=\s*['\"](?:countdown|playing)['\"]", source)
        )
        return {
            # A label/variable alone is not implementation proof.  Require a
            # state mutation plus an observable output or consequence.
            "collect_items": (collect_mutation and collect_trigger) or generic_collect,
            "score_system": score_mutation and collect_trigger and "score:" in source,
            "lives_system": lives_mutation
            and any(x in source for x in ("life", "heart", "<3", "gameover")),
            "enemy_interaction": (
                any(x in source for x in ("obj_cat", "avoid the cat", "avoid cats", "enemy"))
                and any(x in source for x in ("collision", "place_meeting"))
                and (lives_mutation or lose_transition)
            ) or generic_hazard_transition,
            "timer_system": timer_mutation
            and any(x in source for x in ("time:", "alarm[", "gameover")),
            "win_condition": win_transition
            and any(x in source for x in ('phase == "win"', "phase='win'", 'phase = "win"'))
            and any(x in source for x in ("you win", "victory", "all cheese collected")),
            "lose_condition": (
                lose_transition
                and any(x in source for x in ('phase == "gameover"', "phase='gameover'", 'phase = "gameover"'))
                and any(x in source for x in ("game over", "you lose", "defeat"))
            ) or generic_hazard_transition,
            "restart": "play again" in source
            and restart_input
            and (direct_restart_action or start_game_reset),
        }

    @staticmethod
    def _terminal_overlay_visible(shot: Optional[Dict[str, Any]]) -> bool:
        """Detect a prominent red/green terminal banner without an OCR dependency."""
        path = str((shot or {}).get("path") or "")
        if not path or not Path(path).is_file():
            return False
        try:
            from PIL import Image  # type: ignore

            img = Image.open(path).convert("RGB")
            w, h = img.size
            pixels = img.crop((int(w * 0.18), int(h * 0.20), int(w * 0.82), int(h * 0.62))).resize((160, 100))
            vivid = 0
            near_white = 0
            for red, green, blue in pixels.getdata():
                is_red = red >= 175 and red >= green * 1.6 and red >= blue * 1.35
                is_green = green >= 175 and green >= red * 1.45 and green >= blue * 1.25
                if is_red or is_green:
                    vivid += 1
                if red >= 220 and green >= 220 and blue >= 220:
                    near_white += 1
            # Bitmap-font terminal screens such as "YOU LOSE" can be plain
            # white over scenery and are frequently unreadable by OCR.
            # Clouds and pale scenery may contribute a few white pixels; the
            # threshold is intentionally high enough to require a large title.
            return vivid / 16_000 >= 0.008 or near_white / 16_000 >= 0.055
        except OSError:
            return False

    @classmethod
    def _reconcile_cross_modal_results(
        cls,
        *,
        artifact_path: Path,
        results: List[RequirementResult],
        screenshots: List[Dict[str, Any]],
        gameplay_entered: bool,
        restart_observed: bool = False,
    ) -> None:
        """Repair blind pairwise tests using source + accumulated runtime state.

        A GameMaker run is stateful: an earlier test may reach Game Over, making
        later before/after pairs identical. Source evidence alone is not enough;
        promotion requires real gameplay plus a terminal/runtime corroboration.
        """
        if not gameplay_entered or not screenshots:
            return
        signals = cls._source_feature_signals(artifact_path)
        terminal_seen = any(cls._terminal_overlay_visible(shot) for shot in screenshots)
        nonterminal_seen = any(not cls._terminal_overlay_visible(shot) for shot in screenshots)
        if not nonterminal_seen:
            return

        by_id = {row.req_id: row for row in results}

        def promote(req_id: str, *, confidence: float, evidence: List[str]) -> None:
            row = by_id.get(req_id)
            if row is None:
                row = RequirementResult(req_id=req_id, verified=False)
                results.append(row)
                by_id[req_id] = row
            row.verified = True
            row.confidence = max(float(row.confidence or 0), confidence)
            row.reason = ""
            row.verification_basis = "source_runtime_corroboration"
            row.evidence_sources = list(dict.fromkeys([*row.evidence_sources, *evidence]))
            suffix = "cross_modal=source+runtime"
            row.detail = f"{row.detail};{suffix}".strip(";")

        if signals.get("collect_items"):
            promote("collect_items", confidence=0.88, evidence=["gml_collect_trigger_and_mutation", "runtime_gameplay_observed"])
        if signals.get("score_system"):
            promote("score_system", confidence=0.90, evidence=["gml_score_trigger_mutation_and_hud", "runtime_gameplay_observed"])
        if signals.get("lives_system"):
            promote("lives_system", confidence=0.90, evidence=["gml_lives_logic", "runtime_gameplay_observed"])
        if signals.get("enemy_interaction"):
            promote("enemy_interaction", confidence=0.88, evidence=["gml_enemy_life_contract", "runtime_gameplay_observed"])
        if signals.get("timer_system"):
            promote("timer_system", confidence=0.88, evidence=["gml_timer_logic", "runtime_gameplay_observed"])
        if signals.get("win_condition"):
            promote("win_condition", confidence=0.88, evidence=["gml_win_transition_and_ui", "runtime_gameplay_observed"])
        if signals.get("lose_condition"):
            promote("lose_condition", confidence=0.88, evidence=["gml_lose_transition_and_ui", "runtime_gameplay_observed"])
        if signals.get("win_condition") and signals.get("lose_condition"):
            promote("win_lose_condition", confidence=0.90, evidence=["gml_win_and_lose_branches", "runtime_gameplay_observed"])

        restart_observed = restart_observed or any(
            cls._terminal_overlay_visible(row.before_screenshot)
            and row.after_screenshot is not None
            and not cls._terminal_overlay_visible(row.after_screenshot)
            for row in results
        )
        if restart_observed and signals.get("restart"):
            promote("restart", confidence=0.95, evidence=["terminal_before", "gameplay_after_enter", "gml_play_again_contract"])
        elif signals.get("restart"):
            promote("restart", confidence=0.86, evidence=["gml_restart_input_and_full_reset", "runtime_gameplay_observed"])

    def run(
        self,
        *,
        artifact_path: Path,
        process_pid: Optional[int],
        capture_screenshot: Callable[..., Dict[str, Any]],
        plan: Any,
        elapsed_seconds: float,
        gameplay_entered: bool = False,
    ) -> EvidencePackage:
        from app.requirement_extractor import RequirementPlan

        if not isinstance(plan, RequirementPlan):
            raise TypeError("plan must be a RequirementPlan")

        self.gameplay_entered = gameplay_entered
        results: List[RequirementResult] = []
        screenshots: List[Dict[str, Any]] = []
        restart_observed = False
        terminal_state_active = False

        for req in plan.requirements:
            if req.req_id == "menu_navigation" and self.gameplay_entered:
                results.append(
                    RequirementResult(
                        req_id=req.req_id,
                        verified=True,
                        confidence=1.0,
                        reason="",
                        btec_criteria=list(req.btec_criteria),
                        detail="skipped_menu_already_entered",
                    )
                )
                continue

            if not self.gameplay_entered and req.req_id != "menu_navigation":
                results.append(
                    RequirementResult(
                        req_id=req.req_id,
                        verified=False,
                        confidence=0.0,
                        reason="gameplay_not_entered — skipped",
                        btec_criteria=list(req.btec_criteria),
                    )
                )
                continue

            # Requirement tests share one live process.  If the preceding test
            # reached Game Over/Win, recover to gameplay before testing the next
            # mechanic; otherwise every subsequent before/after pair measures
            # the same terminal overlay and produces a cascade of false fails.
            if terminal_state_active and req.req_id != "menu_navigation":
                if (artifact_path.parent / "data.win").is_file():
                    _send_key_win_legacy(0x0D)
                else:
                    _send_key_win(0x0D)
                time.sleep(0.55)
                recovery = self._capture_tagged(
                    artifact_path=artifact_path,
                    process_pid=process_pid,
                    capture_screenshot=capture_screenshot,
                    req_id=req.req_id,
                    phase="terminal_recovery",
                    elapsed_seconds=elapsed_seconds + 0.55,
                )
                screenshots.append(recovery)
                terminal_state_active = self._terminal_overlay_visible(recovery)
                restart_observed = restart_observed or not terminal_state_active

            result = self._test_requirement(
                req,
                artifact_path=artifact_path,
                process_pid=process_pid,
                capture_screenshot=capture_screenshot,
                elapsed_seconds=elapsed_seconds,
            )
            results.append(result)
            if result.before_screenshot:
                screenshots.append(result.before_screenshot)
            if result.after_screenshot:
                screenshots.append(result.after_screenshot)
                terminal_state_active = self._terminal_overlay_visible(result.after_screenshot)
            if req.req_id == "menu_navigation" and result.verified:
                self.gameplay_entered = True

        self._reconcile_cross_modal_results(
            artifact_path=artifact_path,
            results=results,
            screenshots=screenshots,
            gameplay_entered=self.gameplay_entered,
            restart_observed=restart_observed,
        )

        return self._package_from_results(
            submission_id=plan.submission_id,
            gameplay_entered=self.gameplay_entered,
            results=results,
            screenshots=screenshots,
        )


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
    requirement_plan: Optional[Any] = None,
    pro_mode: bool = True,
    engine_id: Optional[str] = None,
    process_crashed: bool = False,
) -> Dict[str, Any]:
    """Menu navigation then requirement-driven playtest — PRO automated L4 path."""
    from app.godot_runtime.retry_policy import GodotRetryPolicy, is_godot_runtime_path

    if is_godot_runtime_path(artifact_path, engine_id=engine_id):
        outcome = GodotRetryPolicy().run(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            elapsed_seconds=elapsed_seconds,
            requirement_plan=requirement_plan,
            pro_mode=pro_mode,
            process_crashed=process_crashed,
        )
        nav_result = outcome.nav_result
        gameplay_entered = outcome.gameplay_entered
        package = outcome.package
        movement = outcome.movement
    else:
        from app.requirement_extractor import RequirementExtractor

        nav = MenuNavigator(max_attempts=MenuNavigator.MAX_ATTEMPTS)
        nav_result = nav.navigate_to_gameplay(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            elapsed_seconds=elapsed_seconds,
        )
        gameplay_entered = nav_result.gameplay_entered
        plan = requirement_plan or RequirementExtractor().default_plan()
        package = PlaytestOrchestrator(pro_mode=pro_mode).run(
            artifact_path=artifact_path,
            process_pid=process_pid,
            capture_screenshot=capture_screenshot,
            plan=plan,
            elapsed_seconds=elapsed_seconds + 2.0,
            gameplay_entered=gameplay_entered,
        )
        # MenuNavigator is only the first attempt. The requirement-driven
        # orchestrator can successfully enter gameplay on its menu_navigation
        # probe (for example after a slow GameMaker countdown). Preserve that
        # authoritative transition instead of keeping the navigator's stale
        # False and zeroing all verified mechanics below.
        gameplay_entered = bool(gameplay_entered or package.gameplay_entered)
        movement = package.to_movement_verification_dict()
        if not gameplay_entered:
            movement["player_movement_verified"] = False
            movement["jump_detected"] = False
            movement["score_change_detected"] = False
            movement["mechanics_verified_count"] = 0
            movement["l4_level"] = "L3"
            movement["automated_l4_level"] = "L3"
        outcome = None

    extra_shots: List[Dict[str, Any]] = []
    if isinstance(nav_result.screenshot, dict):
        extra_shots.append(nav_result.screenshot)
    extra_shots.extend(package.screenshots or movement.get("screenshots") or [])

    gameplay_window_shots = sum(
        1
        for s in extra_shots
        if isinstance(s, dict)
        and s.get("status") == "captured"
        and str(s.get("capture_scope") or "") == "game_window"
    )

    l4_level = calculate_l4_level(
        gameplay_entered=gameplay_entered,
        mechanics_verified_count=int(movement.get("mechanics_verified_count") or 0),
    )
    movement["l4_level"] = l4_level
    movement["automated_l4_level"] = l4_level

    report: Dict[str, Any] = {
        "version": AUTOMATED_GAMEPLAY_VERSION,
        "mode": AUTOMATED_GAMEPLAY_VERSION,
        "authority": "automated_l4_verification",
        "platform": sys.platform,
        "status": "completed",
        "menu_navigation": nav_result.to_dict(),
        "gameplay_entered": gameplay_entered,
        "movement_verification": movement,
        "evidence_package": package.to_dict(),
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
    if outcome is not None:
        report["godot_retry_attempts"] = outcome.retry_attempts
        if outcome.failure is not None:
            report["failure_reason_code"] = outcome.failure.code
            report["failure_reason_ar"] = outcome.failure.reason_ar
            report["failure_evidence"] = outcome.failure.evidence
    # GameMaker does not use the Godot retry outcome, but an unsuccessful
    # input attempt still needs an explicit diagnostic in the report.
    if not report.get("failure_reason_code") and not gameplay_entered:
        from app.godot_runtime.failure_taxonomy import classify_runtime_failure

        terminal = classify_runtime_failure(
            window_detected=process_pid is not None,
            black_screen_duration_s=0,
            gameplay_entered=False,
            mechanics_verified_count=0,
            menu_status=str(nav_result.status or nav_result.visual_state or ""),
            visual_response=False,
            server_dialog_detected=False,
            process_crashed=process_crashed,
            boot_timed_out=False,
        )
        if terminal is not None:
            report["failure_reason_code"] = terminal.code
            report["failure_reason_ar"] = terminal.reason_ar
            report["failure_evidence"] = terminal.evidence
    try:
        from app.runtime_evidence_gate import BTECCriterionMapper

        report["gate_decisions"] = BTECCriterionMapper(grading_mode="pro").evaluate(report)
    except Exception:
        pass
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


def calculate_l4_level(*, gameplay_entered: bool, mechanics_verified_count: int) -> str:
    """L3 / L4_partial / L4_full from gameplay entry and verified mechanic count."""
    if not gameplay_entered:
        return "L3"
    if mechanics_verified_count >= 3:
        return "L4_full"
    if mechanics_verified_count >= 1:
        return "L4_partial"
    return "L3"


def count_test_document_entries(inventory: Dict[str, Any]) -> int:
    """Count test-plan / survey / questionnaire document paths (C.P6 min entries)."""
    paths = inventory.get("intake_relative_paths") or inventory.get("submission_paths") or []
    tokens = (
        "test plan",
        "bug log",
        "استبيان",
        "اختبار",
        "survey",
        "questionnaire",
        "test_plan",
        "testing",
    )
    count = 0
    seen: set[str] = set()
    for raw in paths:
        low = str(raw).lower().replace("\\", "/")
        if low in seen:
            continue
        seen.add(low)
        if any(tok in low for tok in tokens):
            count += 1
            continue
        if low.endswith((".pdf", ".docx", ".doc")) and any(
            x in low for x in ("test", "اختبار", "survey", "استبيان", "plan")
        ):
            count += 1
    assets = inventory.get("assets_detected") or inventory.get(
        "evidence_completeness_gate", {}
    ).get("assets_detected") or {}
    if assets.get("testing_documentation"):
        count = max(count, 2)
    testing = inventory.get("testing_evidence") or {}
    status = str(testing.get("status") or "").lower()
    if status in ("partial", "present", "complete", "detected"):
        count = max(count, 1)
    entries = testing.get("entries") or testing.get("documents") or []
    if isinstance(entries, list) and entries:
        count = max(count, len(entries))
    return count


def assess_automated_l4_gate(
    verification: Optional[Dict[str, Any]],
    *,
    test_document_present: bool = False,
    test_doc_entries: int = 0,
    functional_smoke_pass: bool = False,
    teacher_confirmed: Optional[Dict[str, bool]] = None,
    grading_mode: str | None = None,
    criteria_results: Optional[Sequence[Dict[str, Any]]] = None,
    engine_id: str | None = None,
    student_text: str = "",
) -> Dict[str, Any]:
    """Criterion-level automated L4 gate decisions (Option C policy)."""
    from app.runtime_evidence_gate import BTECCriterionMapper

    gv = verification or {}
    if test_doc_entries <= 0 and test_document_present:
        test_doc_entries = 1
    mapper = BTECCriterionMapper(grading_mode=grading_mode)
    return mapper.evaluate(
        gv,
        test_doc_entries=test_doc_entries,
        teacher_confirmed=teacher_confirmed,
        functional_smoke_pass=functional_smoke_pass,
        criteria_results=criteria_results,
        engine_id=engine_id,
        student_text=student_text,
    )


def _test_document_present(inventory: Dict[str, Any]) -> bool:
    assets = inventory.get("assets_detected") or inventory.get("evidence_completeness_gate", {}).get(
        "assets_detected"
    ) or {}
    # A general report is not a test record.  Treating every DOCX/PDF as C.P6
    # evidence caused ordinary design reports to manufacture one test entry.
    if assets.get("testing_documentation"):
        return True
    paths = inventory.get("intake_relative_paths") or inventory.get("submission_paths") or []
    joined = "\n".join(str(p) for p in paths).lower()
    return any(
        token in joined
        for token in (
            "test plan",
            "test_plan",
            "bug log",
            "bug_log",
            "استبيان",
            "اختبار",
            "survey",
            "questionnaire",
            "testing",
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
    failure_ar = str(gv.get("failure_reason_ar") or "").strip()
    failure_code = str(gv.get("failure_reason_code") or "").strip()
    if failure_ar:
        prefix = f"لا — {failure_code}: {failure_ar}" if failure_code else f"لا — {failure_ar}"
        return prefix
    if gv.get("gameplay_entered") is False:
        menu = gv.get("menu_navigation") or {}
        reason = str(menu.get("status") or menu.get("visual_state") or "unknown")
        return f"لا — لم يدخل gameplay (إطلاق فقط)\nسبب: {reason}"
    if gv.get("gameplay_entered") is not True:
        l4 = str(gv.get("l4_level") or gv.get("automated_l4_level") or "")
        if l4 in ("L4_full", "L4_partial"):
            return f"لا — {l4} غير مؤكد (gameplay_entered غير مثبت)"
    l4 = str(gv.get("l4_level") or gv.get("automated_l4_level") or "")
    if gv.get("gameplay_entered") is True and l4 == "L4_full":
        return (
            "نعم — تم الدخول إلى اللعب الأساسي (L4). "
            "لا يعني ذلك اكتمال اللعبة؛ نتائج الميزات موضحة منفصلة."
        )
    if gv.get("gameplay_entered") is True and l4 == "L4_partial":
        return "نعم — L4 جزئي (تم الدخول إلى gameplay)؛ لا يعني ذلك تحقق كل الميزات أو فتح معيار أكاديمي"
    if (level == "L3" or l4 == "L3") and gv.get("gameplay_entered") is not True:
        return (
            "تم تشغيل ملف اللعبة (L3)، لكن لم يتم إثبات اللعب الفعلي (gameplay) في هذا التقرير. "
            "يمكن اعتماد فيديو تشغيل أو مراجعة بشرية (L5) لإثبات C.P5/C.P6."
        )
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
    grading_mode = None
    if isinstance(grading_result, dict):
        grading_mode = grading_result.get("grading_mode")
    gv_for_gate = dict(gv)
    gv_for_gate["requirement_checklist"] = (
        (grading_result or {}).get("requirement_checklist")
        or inv.get("requirement_checklist")
        or gv.get("requirement_checklist")
        or {}
    )
    gv_for_gate["runtime_evidence_package"] = (
        (grading_result or {}).get("runtime_evidence_package")
        or inv.get("runtime_evidence_package")
        or gv.get("runtime_evidence_package")
        or {}
    )
    gate = assess_automated_l4_gate(
        gv_for_gate,
        test_document_present=_test_document_present(inv),
        test_doc_entries=count_test_document_entries(inv),
        functional_smoke_pass=smoke.get("functional_smoke_pass") is True,
        grading_mode=grading_mode,
    )
    agent_label = format_agent_play_summary_ar(level, gv)
    engine_id = str(obs.get("engine") or "").strip().lower()
    if not engine_id:
        signals = obs.get("signals") if isinstance(obs.get("signals"), dict) else {}
        if signals.get("gamemaker_runtime_verification") or signals.get("gamemaker_observation"):
            engine_id = "gamemaker"
    from app.report_feedback_formatter import build_runtime_outcome

    runtime_outcome = build_runtime_outcome(
        gv, gate, agent_play_label_ar=agent_label, engine_id=engine_id
    )
    return {
        "evidence_level": level,
        "l4_level": gv.get("l4_level") or gate.get("l4_level"),
        "agent_play_label_ar": agent_label,
        "gameplay_agent_used": level in ("L3", "L4", "L5") or bool(gv.get("gameplay_entered")),
        "visual_delta_score": trace.get("visual_delta_score") or gv.get("visual_delta_score"),
        "runtime_verified": level in ("L4", "L5") or gate.get("l4_full") or gate.get("l4_partial"),
        "player_movement_verified": gv.get("player_movement_verified"),
        "automated_l4_gate": gate,
        "gameplay_entered": gv.get("gameplay_entered"),
        "failure_reason_code": gv.get("failure_reason_code"),
        "failure_reason_ar": gv.get("failure_reason_ar"),
        "runtime_outcome": runtime_outcome,
        # Kept for existing snapshots and callers; its contents are now engine-aware.
        "godot_runtime_outcome": runtime_outcome,
    }
