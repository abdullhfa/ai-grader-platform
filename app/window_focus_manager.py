"""Best-effort game-window focused screenshot capture (Windows)."""
from __future__ import annotations

import ctypes
import sys
import threading
import time
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

# GameMaker may temporarily clear its native title during redraw.  Preserve the
# verified HWND per process so capture/focus does not lose the real window after
# the first frame merely because GetWindowTextW returns an empty string.
_WINDOW_HANDLE_CACHE: Dict[int, int] = {}
_WINDOW_RECT_CACHE: Dict[int, Tuple[int, int, int, int]] = {}


def _enable_process_dpi_awareness() -> None:
    """Keep Win32 window rectangles aligned with physical screenshot pixels."""
    try:
        # PER_MONITOR_AWARE_V2; must run before the first window enumeration.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_process_dpi_awareness()


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


def _resolve_game_window_row(
    *,
    artifact_path: Path,
    observed_titles: Optional[Sequence[str]] = None,
    process_pid: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    try:
        all_windows = _enum_windows(process_pid=process_pid)
    except Exception:
        return None
    target_pid = int(process_pid) if process_pid else None
    if not all_windows:
        cached = _WINDOW_HANDLE_CACHE.get(target_pid) if target_pid else None
        if cached and ctypes.windll.user32.IsWindow(cached):
            rect = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(cached, ctypes.byref(rect)):
                bbox = (rect.left, rect.top, rect.right, rect.bottom)
                if _valid_rect(bbox):
                    return {"hwnd": cached, "title": "", "bbox": bbox, "cached": True}
                protected_bbox = _WINDOW_RECT_CACHE.get(target_pid)
                if protected_bbox:
                    return {
                        "hwnd": cached,
                        "title": "",
                        "bbox": protected_bbox,
                        "cached": True,
                        "geometry_degraded": True,
                    }
        return None
    exe_stem = artifact_path.stem.lower()
    preferred = {
        (t or "").strip().lower()
        for t in (observed_titles or [])
        if (t or "").strip()
    }
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
    if target_pid:
        _WINDOW_HANDLE_CACHE[target_pid] = int(best["hwnd"])
        _WINDOW_RECT_CACHE.setdefault(target_pid, tuple(best["bbox"]))
    return dict(best)


def _find_process_window_handle(process_pid: int, artifact_path: Optional[Path]) -> Optional[int]:
    """Find a top-level process window even when minimization invalidates its rect."""
    try:
        user32 = ctypes.windll.user32
        matches: List[Tuple[int, int]] = []
        target_pid = int(process_pid)
        exe_stem = artifact_path.stem.lower() if artifact_path else ""

        def _callback(hwnd: int, _lparam: int) -> bool:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) != target_pid:
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value
            matches.append((_score_window(title, exe_stem), int(hwnd)))
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            _callback
        )
        user32.EnumWindows(enum_proc, 0)
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]
    except Exception:
        return None


def protect_game_window(
    *,
    process_pid: Optional[int] = None,
    hwnd: Optional[int] = None,
    artifact_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Keep the governed game visible and resistant to accidental user closure.

    This deliberately changes only the short-lived student game window. It
    disables the native Close/Minimize commands, restores a minimized/hidden
    window, keeps it topmost, and returns it to its first verified rectangle.
    A force-kill from Task Manager or a Windows secure-desktop transition
    cannot be blocked by a normal user process and remains detectable upstream.
    """
    result: Dict[str, Any] = {
        "window_found": False,
        "restored": False,
        "geometry_restored": False,
        "close_disabled": False,
        "minimize_disabled": False,
        "topmost": False,
    }
    if sys.platform != "win32":
        result["reason"] = "windows_only"
        return result
    try:
        user32 = ctypes.windll.user32
        row: Optional[Dict[str, Any]] = None
        target_hwnd = int(hwnd) if hwnd else None
        if target_hwnd:
            rect = wintypes.RECT()
            if user32.IsWindow(target_hwnd) and user32.GetWindowRect(
                target_hwnd, ctypes.byref(rect)
            ):
                row = {
                    "hwnd": target_hwnd,
                    "bbox": (rect.left, rect.top, rect.right, rect.bottom),
                }
        elif process_pid:
            row = _resolve_game_window_row(
                artifact_path=artifact_path or Path("game.exe"),
                process_pid=process_pid,
            )
            if row:
                target_hwnd = int(row["hwnd"])
            if not target_hwnd:
                cached = _WINDOW_HANDLE_CACHE.get(int(process_pid))
                if cached and user32.IsWindow(cached):
                    target_hwnd = int(cached)
                else:
                    target_hwnd = _find_process_window_handle(
                        int(process_pid), artifact_path
                    )
                    if target_hwnd:
                        _WINDOW_HANDLE_CACHE[int(process_pid)] = int(target_hwnd)
        if not target_hwnd:
            return result

        result["window_found"] = True
        result["hwnd"] = target_hwnd
        was_minimized = bool(user32.IsIconic(target_hwnd))
        was_hidden = not bool(user32.IsWindowVisible(target_hwnd))
        if was_minimized or was_hidden:
            user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
            result["restored"] = True

        # Refresh the rectangle after SW_RESTORE. A minimized HWND commonly
        # reports an off-screen placeholder rectangle and is intentionally
        # absent from the normal capture enumeration.
        rect = wintypes.RECT()
        if user32.GetWindowRect(target_hwnd, ctypes.byref(rect)):
            refreshed_bbox = (rect.left, rect.top, rect.right, rect.bottom)
            if _valid_rect(refreshed_bbox):
                row = {"hwnd": target_hwnd, "bbox": refreshed_bbox}
                if process_pid:
                    _WINDOW_RECT_CACHE.setdefault(int(process_pid), refreshed_bbox)

        # Disable the native system commands used by the X button, Alt+F4,
        # title-bar menu, taskbar menu, and the Minimize button.
        SC_CLOSE = 0xF060
        SC_MINIMIZE = 0xF020
        MF_BYCOMMAND = 0x0000
        MF_GRAYED = 0x0001
        system_menu = user32.GetSystemMenu(target_hwnd, False)
        if system_menu:
            user32.EnableMenuItem(system_menu, SC_CLOSE, MF_BYCOMMAND | MF_GRAYED)
            user32.EnableMenuItem(system_menu, SC_MINIMIZE, MF_BYCOMMAND | MF_GRAYED)
            result["close_disabled"] = True
            result["minimize_disabled"] = True

        # Remove the Minimize caption control as a second line of defense.
        GWL_STYLE = -16
        WS_MINIMIZEBOX = 0x00020000
        style = int(user32.GetWindowLongW(target_hwnd, GWL_STYLE))
        if style & WS_MINIMIZEBOX:
            user32.SetWindowLongW(target_hwnd, GWL_STYLE, style & ~WS_MINIMIZEBOX)
            result["minimize_disabled"] = True

        current_bbox = (
            tuple(row["bbox"])
            if row and not row.get("geometry_degraded")
            else None
        )
        protected_bbox = (
            _WINDOW_RECT_CACHE.get(int(process_pid)) if process_pid else None
        ) or current_bbox
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        SWP_FRAMECHANGED = 0x0020
        # An off-screen/tiny window deliberately drops out of normal capture
        # enumeration. If we still have its first valid rectangle, that absence
        # itself means the geometry must be restored.
        geometry_changed = bool(
            protected_bbox
            and (current_bbox is None or current_bbox != protected_bbox)
        )
        flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE
        left = top = width = height = 0
        move_requested = False
        if geometry_changed and protected_bbox:
            left, top, right, bottom = protected_bbox
            width = max(1, right - left)
            height = max(1, bottom - top)
            move_window = getattr(user32, "MoveWindow", None)
            if move_window is not None:
                move_requested = bool(
                    move_window(
                        target_hwnd,
                        left,
                        top,
                        width,
                        height,
                        True,
                    )
                )
            if not move_requested:
                flags &= ~(SWP_NOMOVE | SWP_NOSIZE)
        user32.SetWindowPos(
            target_hwnd,
            -1,  # HWND_TOPMOST
            left,
            top,
            width,
            height,
            flags,
        )
        if move_requested:
            user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE after MoveWindow
        result["topmost"] = True
        verified_rect = wintypes.RECT()
        geometry_verified = False
        if protected_bbox and user32.GetWindowRect(
            target_hwnd, ctypes.byref(verified_rect)
        ):
            actual_bbox = (
                verified_rect.left,
                verified_rect.top,
                verified_rect.right,
                verified_rect.bottom,
            )
            geometry_verified = actual_bbox == protected_bbox
            result["actual_bbox"] = actual_bbox
        result["geometry_restored"] = bool(geometry_changed and geometry_verified)
        result["bbox"] = protected_bbox
        user32.DrawMenuBar(target_hwnd)
        return result
    except Exception as exc:
        result["error"] = type(exc).__name__
        return result


class RuntimeWindowProtector:
    """Continuously enforce window protection during a governed smoke test."""

    def __init__(
        self,
        process_pid: int,
        *,
        artifact_path: Optional[Path] = None,
        interval_seconds: float = 0.2,
        enable_input_guard: bool = True,
    ) -> None:
        self.process_pid = int(process_pid)
        self.artifact_path = artifact_path
        self.interval_seconds = max(0.05, float(interval_seconds))
        self.enable_input_guard = bool(enable_input_guard)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ticks = 0
        self._window_seen = False
        self._restore_count = 0
        self._geometry_restore_count = 0
        self._close_disabled = False
        self._minimize_disabled = False
        self._topmost = False
        self._last_error = ""
        self._keyboard_hook = None
        self._keyboard_proc = None
        self._keyboard_guard_installed = False
        self._alt_f4_block_count = 0

    def _should_block_alt_f4(self, vk_code: int, flags: int, foreground: int) -> bool:
        target_hwnd = _WINDOW_HANDLE_CACHE.get(self.process_pid)
        return bool(
            target_hwnd
            and int(foreground or 0) == int(target_hwnd)
            and int(vk_code) == 0x73  # VK_F4
            and int(flags) & 0x20  # LLKHF_ALTDOWN
        )

    def _install_keyboard_guard(self) -> None:
        if not self.enable_input_guard or sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            class _KbdLlHookStruct(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            hook_proc_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )

            def _keyboard_callback(n_code: int, w_param: int, l_param: int) -> int:
                if n_code >= 0 and int(w_param) in (0x0100, 0x0104):
                    data = ctypes.cast(
                        l_param, ctypes.POINTER(_KbdLlHookStruct)
                    ).contents
                    if self._should_block_alt_f4(
                        int(data.vkCode),
                        int(data.flags),
                        int(user32.GetForegroundWindow() or 0),
                    ):
                        self._alt_f4_block_count += 1
                        return 1
                return int(
                    user32.CallNextHookEx(
                        self._keyboard_hook or 0,
                        n_code,
                        w_param,
                        l_param,
                    )
                )

            self._keyboard_proc = hook_proc_type(_keyboard_callback)
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                hook_proc_type,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.CallNextHookEx.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            hook = user32.SetWindowsHookExW(
                13,  # WH_KEYBOARD_LL
                self._keyboard_proc,
                kernel32.GetModuleHandleW(None),
                0,
            )
            if hook:
                self._keyboard_hook = hook
                self._keyboard_guard_installed = True
            else:
                self._last_error = (
                    f"SetWindowsHookExW:{int(kernel32.GetLastError())}"
                )
        except Exception as exc:
            self._last_error = type(exc).__name__

    def _uninstall_keyboard_guard(self) -> None:
        if not self._keyboard_hook:
            return
        try:
            ctypes.windll.user32.UnhookWindowsHookEx(self._keyboard_hook)
        except Exception:
            pass
        self._keyboard_hook = None

    def _tick_once(self) -> None:
        state = protect_game_window(
            process_pid=self.process_pid,
            artifact_path=self.artifact_path,
        )
        self._ticks += 1
        self._window_seen = self._window_seen or bool(state.get("window_found"))
        self._restore_count += int(bool(state.get("restored")))
        self._geometry_restore_count += int(bool(state.get("geometry_restored")))
        self._close_disabled = self._close_disabled or bool(state.get("close_disabled"))
        self._minimize_disabled = self._minimize_disabled or bool(
            state.get("minimize_disabled")
        )
        self._topmost = self._topmost or bool(state.get("topmost"))
        if state.get("error"):
            self._last_error = str(state["error"])

    def _run(self) -> None:
        self._install_keyboard_guard()
        last_tick = 0.0
        try:
            while not self._stop.is_set():
                if sys.platform == "win32" and self._keyboard_hook:
                    message = wintypes.MSG()
                    while ctypes.windll.user32.PeekMessageW(
                        ctypes.byref(message), None, 0, 0, 0x0001
                    ):
                        ctypes.windll.user32.TranslateMessage(ctypes.byref(message))
                        ctypes.windll.user32.DispatchMessageW(ctypes.byref(message))
                current_tick = time.monotonic()
                if current_tick - last_tick >= self.interval_seconds:
                    self._tick_once()
                    last_tick = current_tick
                self._stop.wait(0.02)
        finally:
            self._uninstall_keyboard_guard()

    def start(self) -> "RuntimeWindowProtector":
        if self._thread is not None:
            return self
        self._tick_once()
        self._thread = threading.Thread(
            target=self._run,
            name=f"runtime-window-protector-{self.process_pid}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return {
            "process_pid": self.process_pid,
            "monitor_ticks": self._ticks,
            "window_detected": self._window_seen,
            "restore_count": self._restore_count,
            "geometry_restore_count": self._geometry_restore_count,
            "close_disabled": self._close_disabled,
            "minimize_disabled": self._minimize_disabled,
            "topmost_applied": self._topmost,
            "keyboard_guard_installed": self._keyboard_guard_installed,
            "alt_f4_block_count": self._alt_f4_block_count,
            "last_error": self._last_error or None,
            "limitations": [
                "task_manager_force_kill",
                "windows_secure_desktop",
                "shutdown_or_logoff",
                "game_process_crash",
            ],
        }


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
            elif _WINDOW_HANDLE_CACHE.get(int(process_pid)):
                cached = int(_WINDOW_HANDLE_CACHE[int(process_pid)])
                if user32.IsWindow(cached):
                    target_hwnd = cached
        if not target_hwnd:
            return False
        user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(target_hwnd)
        # Pin the short-lived grading window before any early success return.
        # Without this, Chrome/Codex can cover the GameMaker rectangle between
        # SetForegroundWindow and ImageGrab, producing a perfectly valid crop
        # of the wrong application. The governed runtime process is terminated
        # at the end of the smoke session, so the topmost state cannot persist.
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(
            target_hwnd,
            -1,  # HWND_TOPMOST
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
        )
        user32.SetForegroundWindow(target_hwnd)
        if int(user32.GetForegroundWindow() or 0) == int(target_hwnd):
            return True

        try:
            user32.SwitchToThisWindow(target_hwnd, True)
        except Exception:
            pass
        if int(user32.GetForegroundWindow() or 0) == int(target_hwnd):
            return True

        # Windows may reject foreground activation from a background grading
        # worker. Temporarily attach its input queue to the foreground/target
        # threads, then verify the actual foreground handle before reporting
        # success. This is required for GameMaker keyboard polling.
        foreground = user32.GetForegroundWindow()
        # GetCurrentThreadId is exported by kernel32, not user32. Calling it
        # through user32 raises AttributeError and silently aborts the remaining
        # foreground-activation path, leaving GameMaker input and screenshots
        # pointed at whichever desktop app was previously active.
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        foreground_thread = (
            user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )
        target_thread = user32.GetWindowThreadProcessId(target_hwnd, None)
        attached_foreground = False
        attached_target = False
        try:
            if foreground_thread and foreground_thread != current_thread:
                attached_foreground = bool(
                    user32.AttachThreadInput(current_thread, foreground_thread, True)
                )
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    user32.AttachThreadInput(current_thread, target_thread, True)
                )
            user32.BringWindowToTop(target_hwnd)
            user32.SetActiveWindow(target_hwnd)
            user32.SetForegroundWindow(target_hwnd)
            user32.SetFocus(target_hwnd)
        finally:
            if attached_target:
                user32.AttachThreadInput(current_thread, target_thread, False)
            if attached_foreground:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
        if int(user32.GetForegroundWindow() or 0) == int(target_hwnd):
            return True

        # The documented Alt activation gesture unlocks foreground switching
        # for the next call on Windows. Keep it scoped to the selected process
        # window and verify again.
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(target_hwnd)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        if int(user32.GetForegroundWindow() or 0) == int(target_hwnd):
            return True

        # Last-resort user-equivalent title-bar click. This is safer than a
        # client-area click because it cannot activate an in-game control.
        rect = wintypes.RECT()
        if user32.GetWindowRect(target_hwnd, ctypes.byref(rect)):
            cursor = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            user32.SetWindowPos(
                target_hwnd,
                -1,  # HWND_TOPMOST
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.SetCursorPos(rect.left + 60, rect.top + 15)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            ctypes.windll.kernel32.Sleep(120)
            focused_after_click = (
                int(user32.GetForegroundWindow() or 0) == int(target_hwnd)
            )
            user32.SetCursorPos(cursor.x, cursor.y)
            # Keep the short-lived grading game topmost for the rest of its
            # smoke session.  Releasing it immediately let the browser/Codex
            # cover the rectangle between focus and ImageGrab, and keyboard
            # events then went to the wrong application.  The process is
            # terminated at the end of the governed session.
            if focused_after_click:
                return True
        return int(user32.GetForegroundWindow() or 0) == int(target_hwnd)
    except Exception:
        return False


def resolve_game_window_bbox(
    *,
    artifact_path: Path,
    observed_titles: Optional[Sequence[str]] = None,
    process_pid: Optional[int] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """Pick most likely game window bbox from desktop windows."""
    row = _resolve_game_window_row(
        artifact_path=artifact_path,
        observed_titles=observed_titles,
        process_pid=process_pid,
    )
    return row.get("bbox") if row else None


def _capture_window_surface(hwnd: int, width: int, height: int):
    """Render an HWND into a Pillow image without relying on pywin32.

    PrintWindow asks DWM for the owning window surface, so the image remains the
    game even when Codex, Chrome, or another top-level window overlaps it.
    """
    if width <= 0 or height <= 0:
        return None
    try:
        from PIL import Image  # type: ignore

        class _BitmapInfoHeader(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class _BitmapInfo(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", _BitmapInfoHeader),
                ("bmiColors", wintypes.DWORD * 3),
            ]

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        handle_t = ctypes.c_void_p
        user32.GetWindowDC.argtypes = [wintypes.HWND]
        user32.GetWindowDC.restype = handle_t
        user32.ReleaseDC.argtypes = [wintypes.HWND, handle_t]
        gdi32.CreateCompatibleDC.argtypes = [handle_t]
        gdi32.CreateCompatibleDC.restype = handle_t
        gdi32.CreateCompatibleBitmap.argtypes = [handle_t, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = handle_t
        gdi32.SelectObject.argtypes = [handle_t, handle_t]
        gdi32.SelectObject.restype = handle_t
        gdi32.DeleteObject.argtypes = [handle_t]
        gdi32.DeleteDC.argtypes = [handle_t]
        user32.PrintWindow.argtypes = [wintypes.HWND, handle_t, wintypes.UINT]
        user32.PrintWindow.restype = wintypes.BOOL
        gdi32.GetDIBits.argtypes = [
            handle_t,
            handle_t,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.c_void_p,
            ctypes.POINTER(_BitmapInfo),
            wintypes.UINT,
        ]
        gdi32.GetDIBits.restype = ctypes.c_int

        window_dc = user32.GetWindowDC(hwnd)
        if not window_dc:
            return None
        memory_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        old_object = gdi32.SelectObject(memory_dc, bitmap) if memory_dc and bitmap else None
        try:
            if not memory_dc or not bitmap:
                return None
            # PW_RENDERFULLCONTENT (2) renders the real DWM surface.
            if int(user32.PrintWindow(hwnd, memory_dc, 2)) != 1:
                return None
            info = _BitmapInfo()
            info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
            info.bmiHeader.biWidth = width
            # Negative height requests a top-down DIB (no vertical flip).
            info.bmiHeader.biHeight = -height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0  # BI_RGB
            pixels = ctypes.create_string_buffer(width * height * 4)
            lines = gdi32.GetDIBits(
                memory_dc,
                bitmap,
                0,
                height,
                pixels,
                ctypes.byref(info),
                0,  # DIB_RGB_COLORS
            )
            if int(lines) != height:
                return None
            return Image.frombuffer(
                "RGB",
                (width, height),
                pixels,
                "raw",
                "BGRX",
                0,
                1,
            ).copy()
        finally:
            if old_object:
                gdi32.SelectObject(memory_dc, old_object)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(hwnd, window_dc)
    except Exception:
        return None


def capture_game_window_image(
    *,
    artifact_path: Path,
    process_pid: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Capture the process window surface even when another app overlaps it."""
    row = _resolve_game_window_row(
        artifact_path=artifact_path,
        process_pid=process_pid,
    )
    if not row:
        return None
    hwnd = int(row["hwnd"])
    left, top, right, bottom = tuple(row["bbox"])
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None
    image = _capture_window_surface(hwnd, width, height)
    if image is not None:
        return {
            "image": image,
            "bbox": (left, top, right, bottom),
            "hwnd": hwnd,
            "method": "win32_printwindow_ctypes",
        }
    try:
        import win32gui  # type: ignore
        import win32ui  # type: ignore
        from PIL import Image  # type: ignore

        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        memory_dc = source_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source_dc, width, height)
        memory_dc.SelectObject(bitmap)
        try:
            # PW_RENDERFULLCONTENT asks DWM to render the real window surface,
            # not the pixels belonging to whichever application overlaps it.
            rendered = int(user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2))
            if rendered != 1:
                return None
            bits = bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (width, height),
                bits,
                "raw",
                "BGRX",
                0,
                1,
            ).copy()
            return {
                "image": image,
                "bbox": (left, top, right, bottom),
                "hwnd": hwnd,
                "method": "win32_printwindow",
            }
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception:
        return None


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
