"""
Stage 5 — Automated interaction trace (advisory only).

Sends bounded keyboard/mouse input during L4 smoke observation and compares
visual delta before/after. Does NOT verify gameplay or unlock Achieved.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

INTERACTION_BURST_VERSION = "automated_interaction_burst_v1"
INTERACTION_AT_SECONDS = 3.5
INTERACTION_KEY_HOLD_MS = 45
INTERACTION_GAP_MS = 60

# Bounded input script — generic WASD + Space + Enter + center click
DEFAULT_KEY_VKS: Tuple[Tuple[str, int], ...] = (
    ("W", 0x57),
    ("A", 0x41),
    ("S", 0x53),
    ("D", 0x44),
    ("SPACE", 0x20),
    ("ENTER", 0x0D),
)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


def _visual_delta_score(pre_path: str, post_path: str) -> Optional[float]:
    if not pre_path or not post_path:
        return None
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        pre = Image.open(pre_path).convert("RGB").resize((32, 32))
        post = Image.open(post_path).convert("RGB").resize((32, 32))
        diff = sum(
            abs(int(a[i]) - int(b[i]))
            for a, b in zip(list(pre.getdata()), list(post.getdata()))
            for i in range(min(len(a), len(b)))
        ) / (32 * 32 * 3)
        return round(diff, 3)
    except OSError:
        return None


def _visual_delta_from_stats(pre: Dict[str, Any], post: Dict[str, Any]) -> Optional[float]:
    keys = ("avg_luma_approx", "luma_variance", "entropy_approx", "center_band_variance")
    deltas: List[float] = []
    for key in keys:
        try:
            a = float(pre.get(key) or 0)
            b = float(post.get(key) or 0)
        except (TypeError, ValueError):
            continue
        deltas.append(abs(a - b))
    if not deltas:
        return None
    return round(sum(deltas) / len(deltas), 3)


def classify_visual_response_to_input(
    *,
    delta_score: Optional[float] = None,
    pre_stats: Optional[Dict[str, Any]] = None,
    post_stats: Optional[Dict[str, Any]] = None,
    pre_path: str = "",
    post_path: str = "",
) -> str:
    """
    Coarse visual response — none | partial | unknown.
    Never returns 'yes' (gameplay verified).
    """
    score = delta_score
    if score is None and pre_path and post_path:
        score = _visual_delta_score(pre_path, post_path)
    if score is None and pre_stats and post_stats:
        score = _visual_delta_from_stats(pre_stats, post_stats)
    if score is None:
        return "unknown"
    if score >= 6.0:
        return "partial"
    if score >= 2.5:
        return "partial"
    return "none"


def _send_key_win(vk: int, *, hold_ms: int = INTERACTION_KEY_HOLD_MS) -> bool:
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

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    def _input_key(flags: int) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        return inp

    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(_input_key(0)), ctypes.sizeof(INPUT))
    if not sent:
        return False
    time.sleep(max(hold_ms, 10) / 1000.0)
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(_input_key(KEYEVENTF_KEYUP)), ctypes.sizeof(INPUT))
    return bool(sent)


def _click_center_win() -> bool:
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    def _mouse(flags: int) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
        return inp

    down = ctypes.windll.user32.SendInput(1, ctypes.byref(_mouse(MOUSEEVENTF_LEFTDOWN)), ctypes.sizeof(INPUT))
    up = ctypes.windll.user32.SendInput(1, ctypes.byref(_mouse(MOUSEEVENTF_LEFTUP)), ctypes.sizeof(INPUT))
    return bool(down and up)


def run_interaction_burst() -> Dict[str, Any]:
    """
    Execute bounded keyboard/mouse burst. Best-effort; game window focus not guaranteed.
    """
    record: Dict[str, Any] = {
        "mode": INTERACTION_BURST_VERSION,
        "authority": "advisory_observation_only",
        "platform": sys.platform,
        "status": "unavailable",
        "inputs_sent": [],
        "input_count": 0,
        "mouse_click_attempted": False,
        "errors": [],
        "does_not_verify_gameplay": True,
        "human_playtest_required": True,
        "authority_note_ar": (
            "تفاعل آلي محدود — يسجّل إرسال input ومقارنة visual delta فقط؛ "
            "لا يثبت player movement ولا gameplay correctness."
        ),
    }
    if sys.platform != "win32":
        record["errors"].append("interaction_trace_windows_only")
        return record

    sent_inputs: List[Dict[str, Any]] = []
    try:
        for label, vk in DEFAULT_KEY_VKS:
            ok = _send_key_win(vk)
            sent_inputs.append({"type": "key", "key": label, "vk": vk, "sent": ok})
            time.sleep(INTERACTION_GAP_MS / 1000.0)
        mouse_ok = _click_center_win()
        record["mouse_click_attempted"] = True
        sent_inputs.append({"type": "mouse", "action": "left_click_center", "sent": mouse_ok})
        record["inputs_sent"] = sent_inputs
        record["input_count"] = len(sent_inputs)
        record["status"] = "completed" if any(i.get("sent") for i in sent_inputs) else "partial"
    except Exception as exc:
        record["errors"].append(str(exc))
        record["status"] = "partial" if sent_inputs else "failed"
        record["inputs_sent"] = sent_inputs
        record["input_count"] = len(sent_inputs)
    return record


def build_interaction_trace_report(
    burst: Dict[str, Any],
    *,
    pre_screenshot: Optional[Dict[str, Any]] = None,
    post_screenshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge burst record with before/after visual comparison."""
    report = dict(burst)
    pre = pre_screenshot or {}
    post = post_screenshot or {}
    pre_path = str(pre.get("path") or "")
    post_path = str(post.get("path") or "")
    pre_stats = pre.get("visual_stats") if isinstance(pre.get("visual_stats"), dict) else {}
    post_stats = post.get("visual_stats") if isinstance(post.get("visual_stats"), dict) else {}

    delta = _visual_delta_score(pre_path, post_path)
    if delta is None:
        delta = _visual_delta_from_stats(pre_stats, post_stats)

    response = classify_visual_response_to_input(
        delta_score=delta,
        pre_stats=pre_stats,
        post_stats=post_stats,
        pre_path=pre_path,
        post_path=post_path,
    )
    report.update({
        "pre_interaction_label": pre.get("label") or pre.get("capture_type") or "",
        "post_interaction_label": post.get("label") or post.get("capture_type") or "post_interaction",
        "pre_interaction_path": pre_path,
        "post_interaction_path": post_path,
        "visual_delta_score": delta,
        "visual_response_to_input": response,
        "interaction_traces_detected": burst.get("status") == "completed",
        "player_movement_verified": False,
    })
    return report


def apply_interaction_signals(signals: Dict[str, Any], trace: Dict[str, Any]) -> None:
    """
    Mutate smoke signals in-place — never sets player_moved=detected from automation.
    """
    if not trace:
        return
    if trace.get("status") in ("completed", "partial"):
        signals["interaction_input_sent"] = "yes"
    else:
        signals["interaction_input_sent"] = "no"
    signals["visual_response_to_input"] = trace.get("visual_response_to_input", "unknown")
    signals["automated_interaction_observed"] = (
        "yes"
        if trace.get("interaction_traces_detected")
        or trace.get("status") in ("completed", "partial")
        else "no"
    )
    if trace.get("player_movement_verified"):
        signals["player_moved"] = "detected"
    elif signals.get("player_moved") in (None, ""):
        signals["player_moved"] = "unknown"
