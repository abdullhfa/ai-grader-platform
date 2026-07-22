"""Process-bound deterministic GameMaker menu navigation."""
from __future__ import annotations

import hashlib
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, Tuple

WindowRect = Tuple[int, int, int, int]
DEFAULT_TEMPLATE = Path(__file__).resolve().parents[3] / "assets" / "templates" / "gamemaker" / "easy_lv1_button.png"


class MenuNavResult(str, Enum):
    WINDOW_NOT_READY = "WINDOW_NOT_READY"
    BUTTON_NOT_FOUND = "BUTTON_NOT_FOUND"
    NO_SCENE_CHANGE_DETECTED = "NO_SCENE_CHANGE_DETECTED"
    WINDOW_LOST = "WINDOW_LOST"
    GAMEPLAY_ENTERED = "GAMEPLAY_ENTERED"


class WindowAdapter(Protocol):
    def is_window(self, hwnd: int) -> bool: ...
    def get_rect(self, hwnd: int) -> Optional[WindowRect]: ...
    def capture(self, hwnd: int) -> Any: ...
    def click_client(self, hwnd: int, point: Tuple[int, int]) -> bool: ...


class Win32WindowAdapter:
    """Uses HWND-only capture and client-coordinate click messages."""
    def is_window(self, hwnd: int) -> bool:
        try:
            import ctypes
            return bool(hwnd and ctypes.windll.user32.IsWindow(hwnd))
        except Exception:
            return False

    def get_rect(self, hwnd: int) -> Optional[WindowRect]:
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            result = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            return result if result[2] > result[0] and result[3] > result[1] else None
        except Exception:
            return None

    def capture(self, hwnd: int) -> Any:
        if not self.is_window(hwnd):
            return None
        try:
            from PIL import ImageGrab
            return ImageGrab.grab(window=hwnd)
        except Exception:
            return None

    def click_client(self, hwnd: int, point: Tuple[int, int]) -> bool:
        if not self.is_window(hwnd):
            return False
        try:
            import ctypes
            from ctypes import wintypes
            client = wintypes.POINT(*point)
            user32 = ctypes.windll.user32
            if not user32.ScreenToClient(hwnd, ctypes.byref(client)):
                return False
            lparam = (int(client.y) << 16) | (int(client.x) & 0xFFFF)
            return bool(user32.PostMessageW(hwnd, 0x0201, 0x0001, lparam) and user32.PostMessageW(hwnd, 0x0202, 0, lparam))
        except Exception:
            return False


def _as_bgr(frame: Any) -> Any:
    try:
        import cv2
        import numpy as np
        array = np.asarray(frame)
        if array.ndim == 2:
            return array
        if array.ndim == 3 and array.shape[2] == 4:
            return cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
        if array.ndim == 3:
            return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    except Exception:
        pass
    return None


def locate_button_by_template(window_rect: WindowRect, template_path: Path, confidence: float = 0.85, *, frame: Any = None) -> Optional[Tuple[int, int]]:
    """Locate a template in a frame captured from the target HWND.

    The function fails closed without ``frame``: it never captures the desktop
    merely because it was given a rectangle.
    """
    if frame is None or not Path(template_path).is_file():
        return None
    try:
        import cv2
        image, template = _as_bgr(frame), cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if image is None or template is None:
            return None
        ih, iw = image.shape[:2]
        th, tw = template.shape[:2]
        if th > ih or tw > iw:
            return None
        _, score, _, top_left = cv2.minMaxLoc(cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED))
        if float(score) < confidence:
            return None
        left, top, _, _ = window_rect
        return (left + int(top_left[0]) + tw // 2, top + int(top_left[1]) + th // 2)
    except Exception:
        return None


def _frame_hash(frame: Any) -> Optional[str]:
    data = _as_bgr(frame)
    return hashlib.sha256(data.tobytes()).hexdigest() if data is not None else None


def _frames_differ(before: Any, after: Any, threshold: float = 3.0) -> bool:
    try:
        import cv2
        import numpy as np
        a, b = _as_bgr(before), _as_bgr(after)
        if a is None or b is None:
            return False
        return a.shape != b.shape or float(np.mean(cv2.absdiff(a, b))) >= threshold
    except Exception:
        return False


def wait_for_window_stable(hwnd: int, timeout_s: float = 3, *, adapter: Optional[WindowAdapter] = None) -> bool:
    adapter = adapter or Win32WindowAdapter()
    deadline, previous = time.monotonic() + timeout_s, None
    while time.monotonic() < deadline:
        if not adapter.is_window(hwnd):
            return False
        rect, digest = adapter.get_rect(hwnd), _frame_hash(adapter.capture(hwnd))
        if rect is None or digest is None:
            return False
        if previous == (rect, digest):
            return True
        previous = (rect, digest)
        time.sleep(0.12)
    return False


def click_at(point: Tuple[int, int], hwnd: int, *, adapter: Optional[WindowAdapter] = None) -> bool:
    adapter = adapter or Win32WindowAdapter()
    return bool(adapter.is_window(hwnd) and adapter.click_client(hwnd, point))


def wait_for_gameplay_change(hwnd: int, timeout_s: float = 4, *, before_frame: Any = None, adapter: Optional[WindowAdapter] = None) -> MenuNavResult:
    adapter = adapter or Win32WindowAdapter()
    if not adapter.is_window(hwnd):
        return MenuNavResult.WINDOW_LOST
    if before_frame is None:
        return MenuNavResult.NO_SCENE_CHANGE_DETECTED
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not adapter.is_window(hwnd):
            return MenuNavResult.WINDOW_LOST
        after = adapter.capture(hwnd)
        if after is None:
            return MenuNavResult.WINDOW_LOST
        if _frames_differ(before_frame, after):
            return MenuNavResult.GAMEPLAY_ENTERED
        time.sleep(0.15)
    return MenuNavResult.NO_SCENE_CHANGE_DETECTED


def navigate_menu_deterministic(hwnd: int, window_rect: WindowRect, *, template_path: Path = DEFAULT_TEMPLATE, confidence: float = 0.85, adapter: Optional[WindowAdapter] = None) -> MenuNavResult:
    adapter = adapter or Win32WindowAdapter()
    if not adapter.is_window(hwnd):
        return MenuNavResult.WINDOW_LOST
    if adapter.get_rect(hwnd) != window_rect:
        return MenuNavResult.WINDOW_NOT_READY
    if not wait_for_window_stable(hwnd, adapter=adapter):
        return MenuNavResult.WINDOW_LOST if not adapter.is_window(hwnd) else MenuNavResult.WINDOW_NOT_READY
    before = adapter.capture(hwnd)
    if before is None:
        return MenuNavResult.WINDOW_LOST
    point = locate_button_by_template(window_rect, template_path, confidence, frame=before)
    if point is None:
        return MenuNavResult.BUTTON_NOT_FOUND
    if not click_at(point, hwnd, adapter=adapter):
        return MenuNavResult.WINDOW_LOST if not adapter.is_window(hwnd) else MenuNavResult.WINDOW_NOT_READY
    return wait_for_gameplay_change(hwnd, before_frame=before, adapter=adapter)
