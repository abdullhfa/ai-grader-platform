"""Best-effort game-window focused screenshot capture (Windows)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_KEYWORDS = (
    "godot",
    "unity",
    "gamemaker",
    "scratch",
    "pygame",
    "game",
)


def _valid_rect(rect: Tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = rect
    return right > left and bottom > top and (right - left) >= 320 and (bottom - top) >= 200


def _score_window(title: str, exe_stem: str) -> int:
    t = (title or "").strip().lower()
    score = 0
    if not t:
        return score
    if exe_stem and exe_stem in t:
        score += 80
    if any(k in t for k in _KEYWORDS):
        score += 40
    if "chrome" in t or "edge" in t or "firefox" in t:
        score -= 60
    if "visual studio" in t or "cursor" in t:
        score -= 40
    return score


def _enum_windows(*, process_pid: Optional[int] = None) -> List[Dict[str, Any]]:
    user32 = ctypes.windll.user32
    windows: List[Dict[str, Any]] = []
    target_pid = int(process_pid) if process_pid else None

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if target_pid is not None:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) != target_pid:
                return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value or ""
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
        if not _valid_rect(bbox):
            return True
        windows.append({"hwnd": hwnd, "title": title, "bbox": bbox})
        return True

    user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return windows


def focus_game_window(*, process_pid: Optional[int] = None, hwnd: Optional[int] = None) -> bool:
    """Best-effort bring game window to foreground before capture."""
    try:
        user32 = ctypes.windll.user32
        target_hwnd = hwnd
        if target_hwnd is None and process_pid:
            rows = _enum_windows(process_pid=process_pid)
            if rows:
                target_hwnd = int(rows[0]["hwnd"])
        if not target_hwnd:
            return False
        user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(target_hwnd)
        return True
    except Exception:
        return False


def resolve_game_window_handle(*, artifact_path: Path, process_pid: Optional[int] = None) -> Optional[int]:
    """Resolve one process-owned game HWND; never select an unrelated desktop window."""
    try:
        rows = _enum_windows(process_pid=process_pid)
    except Exception:
        return None
    if not rows:
        return None
    scored = sorted(
        ((_score_window(str(row.get("title") or ""), artifact_path.stem.lower()), row) for row in rows),
        key=lambda item: item[0], reverse=True,
    )
    return int(scored[0][1]["hwnd"]) if scored and scored[0][0] >= 25 else None


def pin_game_window_for_sandbox(*, artifact_path: Path, process_pid: Optional[int] = None) -> bool:
    """Keep the process-owned game window foregrounded inside an approved sandbox.

    This deliberately does not run on a host desktop: pinning/minimising controls
    outside a sandbox would interfere with the teacher's own applications.
    """
    import os
    if os.environ.get("AI_GRADER_WINDOWS_SANDBOX") != "1":
        return False
    try:
        hwnd = resolve_game_window_handle(artifact_path=artifact_path, process_pid=process_pid)
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # TOPMOST, no move/resize
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def resolve_game_window_bbox(
    *,
    artifact_path: Path,
    observed_titles: Optional[Sequence[str]] = None,
    process_pid: Optional[int] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """Pick most likely game window bbox from desktop windows."""
    try:
        all_windows = _enum_windows(process_pid=process_pid)
    except Exception:
        return None
    if not all_windows:
        return None
    exe_stem = artifact_path.stem.lower()
    preferred = {(t or "").strip().lower() for t in (observed_titles or []) if (t or "").strip()}
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for row in all_windows:
        title = str(row.get("title") or "")
        score = _score_window(title, exe_stem)
        if title.lower() in preferred:
            score += 30
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    if best_score < 25:
        return None
    return best.get("bbox")


def classify_capture_scope(
    *,
    capture_bbox: Optional[Tuple[int, int, int, int]],
    game_bbox: Optional[Tuple[int, int, int, int]],
) -> str:
    if not capture_bbox:
        return "unknown"
    if not game_bbox:
        return "desktop_fallback"
    if capture_bbox == game_bbox:
        return "game_window"
    return "partial_window"
