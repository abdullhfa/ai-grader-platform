"""Process-bound deterministic GameMaker menu navigation."""
from __future__ import annotations

import hashlib
import time
from enum import Enum
from pathlib import Path
from .readiness import ReadinessReason, evaluate_readiness
from .win32_input import INPUT, build_enter_inputs, interpret_sendinput_result
from typing import Any, Optional, Protocol, Tuple

WindowRect = Tuple[int, int, int, int]
DEFAULT_TEMPLATE = Path(__file__).resolve().parents[3] / "assets" / "templates" / "gamemaker" / "easy_lv1_button.png"


class MenuNavResult(str, Enum):
    WINDOW_NOT_READY = "WINDOW_NOT_READY"
    BUTTON_NOT_FOUND = "BUTTON_NOT_FOUND"
    NO_SCENE_CHANGE_DETECTED = "NO_SCENE_CHANGE_DETECTED"
    WINDOW_LOST = "WINDOW_LOST"
    CAPTURE_DIMENSION_MISMATCH = "CAPTURE_DIMENSION_MISMATCH"
    CAPTURE_UNUSABLE = "CAPTURE_UNUSABLE"
    FOREGROUND_NOT_CONFIRMED = "FOREGROUND_NOT_CONFIRMED"
    GAMEPLAY_ENTERED = "GAMEPLAY_ENTERED"


class WindowAdapter(Protocol):
    """Structural contract for process-bound window operations."""
    def is_window(self, hwnd: int) -> bool: ...
    def get_rect(self, hwnd: int) -> Optional[WindowRect]: ...
    def get_client_rect(self, hwnd: int) -> Optional[WindowRect]: ...
    def capture(self, hwnd: int) -> Any: ...
    def activate_and_confirm(self, hwnd: int) -> bool: ...
    def send_enter(self, hwnd: int) -> bool: ...
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

    def get_client_rect(self, hwnd: int) -> Optional[WindowRect]:
        """Return the HWND client area in screen coordinates."""
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            user32 = ctypes.windll.user32
            if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return None
            top_left = wintypes.POINT(rect.left, rect.top)
            bottom_right = wintypes.POINT(rect.right, rect.bottom)
            if not user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
                return None
            if not user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
                return None
            result = (int(top_left.x), int(top_left.y), int(bottom_right.x), int(bottom_right.y))
            return result if result[2] > result[0] and result[3] > result[1] else None
        except Exception:
            return None

    def capture(self, hwnd: int) -> Any:
        """Capture only the HWND client surface; never fall back to desktop capture."""
        if not self.is_window(hwnd):
            return None
        self.last_capture_result = None
        try:
            import ctypes
            from ctypes import wintypes
            from PIL import Image
            client_rect = self.get_client_rect(hwnd)
            if client_rect is None:
                return None
            width = client_rect[2] - client_rect[0]
            height = client_rect[3] - client_rect[1]

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

            class RGBQUAD(ctypes.Structure):
                _fields_ = [("rgbBlue", ctypes.c_ubyte), ("rgbGreen", ctypes.c_ubyte), ("rgbRed", ctypes.c_ubyte), ("rgbReserved", ctypes.c_ubyte)]

            class BITMAPINFO(ctypes.Structure):
                _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD)]

            user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
            user32.GetDC.argtypes = (ctypes.c_void_p,)
            user32.GetDC.restype = ctypes.c_void_p
            user32.ReleaseDC.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            gdi32.CreateCompatibleDC.argtypes = (ctypes.c_void_p,)
            gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
            gdi32.CreateDIBSection.argtypes = (ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD)
            gdi32.CreateDIBSection.restype = ctypes.c_void_p
            gdi32.SelectObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            gdi32.SelectObject.restype = ctypes.c_void_p
            gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
            gdi32.DeleteDC.argtypes = (ctypes.c_void_p,)
            user32.PrintWindow.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
            user32.PrintWindow.restype = wintypes.BOOL
            window_dc = user32.GetDC(hwnd)
            if not window_dc:
                return None
            memory_dc = bitmap = previous = None
            try:
                memory_dc = gdi32.CreateCompatibleDC(window_dc)
                if not memory_dc:
                    return None
                info = BITMAPINFO()
                info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                info.bmiHeader.biWidth = width
                info.bmiHeader.biHeight = -height
                info.bmiHeader.biPlanes = 1
                info.bmiHeader.biBitCount = 32
                info.bmiHeader.biCompression = 0
                bits = ctypes.c_void_p()
                bitmap = gdi32.CreateDIBSection(memory_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
                if not bitmap or not bits.value:
                    return None
                previous = gdi32.SelectObject(memory_dc, bitmap)
                if not user32.PrintWindow(hwnd, memory_dc, 0x00000003):  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
                    return None
                image = Image.frombuffer("RGBA", (width, height), ctypes.string_at(bits, width * height * 4), "raw", "BGRA", 0, 1).convert("RGB")
                if image.size != (width, height):
                    self.last_capture_result = MenuNavResult.CAPTURE_DIMENSION_MISMATCH
                    return None
                if all(low == high for low, high in image.getextrema()):
                    self.last_capture_result = MenuNavResult.CAPTURE_UNUSABLE
                    return None
                return image
            finally:
                if previous and memory_dc:
                    gdi32.SelectObject(memory_dc, previous)
                if bitmap:
                    gdi32.DeleteObject(bitmap)
                if memory_dc:
                    gdi32.DeleteDC(memory_dc)
                user32.ReleaseDC(hwnd, window_dc)
        except Exception:
            return None

    def activate_and_confirm(self, hwnd: int) -> bool:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow(hwnd)
            return int(user32.GetForegroundWindow()) == int(hwnd)
        except Exception:
            return False

    def send_enter(self, hwnd: int) -> bool:
        """Use SendInput, not window messages, for GameMaker keyboard polling."""
        if not self.is_window(hwnd):
            return False
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            inputs = build_enter_inputs()
            user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
            user32.SendInput.restype = wintypes.UINT
            ctypes.set_last_error(0)
            returned_count = int(user32.SendInput(2, inputs, ctypes.sizeof(INPUT)))
            self.last_sendinput_result = {**interpret_sendinput_result(returned_count, ctypes.get_last_error()), 'cb_size': ctypes.sizeof(INPUT)}
            return self.last_sendinput_result['success']
        except Exception:
            return False
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


def _frame_dimensions(frame: Any) -> Optional[Tuple[int, int]]:
    try:
        if hasattr(frame, "size") and isinstance(frame.size, tuple):
            return (int(frame.size[0]), int(frame.size[1]))
        data = _as_bgr(frame)
        return (int(data.shape[1]), int(data.shape[0])) if data is not None else None
    except Exception:
        return None


def _capture_for_client(hwnd: int, adapter: WindowAdapter) -> Tuple[Any, Optional[WindowRect], Optional[MenuNavResult]]:
    if not adapter.is_window(hwnd):
        return None, None, MenuNavResult.WINDOW_LOST
    client_rect = adapter.get_client_rect(hwnd)
    if client_rect is None:
        return None, None, MenuNavResult.WINDOW_LOST
    frame = adapter.capture(hwnd)
    if frame is None:
        return None, client_rect, getattr(adapter, "last_capture_result", None) or MenuNavResult.WINDOW_LOST
    expected = (client_rect[2] - client_rect[0], client_rect[3] - client_rect[1])
    if _frame_dimensions(frame) != expected:
        return None, client_rect, MenuNavResult.CAPTURE_DIMENSION_MISMATCH

    return frame, client_rect, None


def _wait_for_window_stable_result(hwnd: int, timeout_s: float = 3, *, adapter: WindowAdapter) -> Optional[MenuNavResult]:
    deadline, previous = time.monotonic() + timeout_s, None
    while time.monotonic() < deadline:
        frame, _, result = _capture_for_client(hwnd, adapter)
        if result is not None:
            return result
        rect, digest = adapter.get_rect(hwnd), _frame_hash(frame)
        if rect is None or digest is None:
            return MenuNavResult.WINDOW_NOT_READY
        if previous == (rect, digest):
            return None
        previous = (rect, digest)
        time.sleep(0.12)
    return MenuNavResult.WINDOW_NOT_READY


def wait_for_window_stable(hwnd: int, timeout_s: float = 3, *, adapter: Optional[WindowAdapter] = None) -> bool:
    adapter = adapter or Win32WindowAdapter()
    return _wait_for_window_stable_result(hwnd, timeout_s, adapter=adapter) is None


def click_at(point: Tuple[int, int], hwnd: int, *, adapter: Optional[WindowAdapter] = None) -> bool:
    adapter = adapter or Win32WindowAdapter()
    return bool(adapter.is_window(hwnd) and adapter.click_client(hwnd, point))


def wait_for_gameplay_change(hwnd: int, timeout_s: float = 4, *, before_frame: Any = None, adapter: Optional[WindowAdapter] = None) -> MenuNavResult:
    adapter = adapter or Win32WindowAdapter()
    if before_frame is None:
        return MenuNavResult.NO_SCENE_CHANGE_DETECTED
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        after, _, result = _capture_for_client(hwnd, adapter)
        if result is not None:
            return result
        if _frames_differ(before_frame, after):
            return MenuNavResult.GAMEPLAY_ENTERED
        time.sleep(0.15)
    return MenuNavResult.NO_SCENE_CHANGE_DETECTED


def navigate_menu_deterministic(hwnd: int, window_rect: WindowRect, *, template_path: Path = DEFAULT_TEMPLATE, confidence: float = 0.85, menu_timeout_s: float = 5, adapter: Optional[WindowAdapter] = None) -> MenuNavResult:
    adapter = adapter or Win32WindowAdapter()
    if not adapter.is_window(hwnd):
        return MenuNavResult.WINDOW_LOST
    if adapter.get_rect(hwnd) != window_rect:
        return MenuNavResult.WINDOW_NOT_READY
    readiness = evaluate_readiness(hwnd, window_rect, adapter)
    setattr(adapter, "last_readiness_result", readiness)
    if not readiness.ready:
        readiness_mapping = {
            ReadinessReason.HWND_INVALID: MenuNavResult.WINDOW_LOST,
            ReadinessReason.CAPTURE_FAILED: MenuNavResult.WINDOW_LOST,
            ReadinessReason.CAPTURE_SIZE_MISMATCH: MenuNavResult.CAPTURE_DIMENSION_MISMATCH,
        }
        return readiness_mapping.get(readiness.reason_code, MenuNavResult.WINDOW_NOT_READY)
    deadline = time.monotonic() + menu_timeout_s
    before = client_rect = point = None
    while time.monotonic() < deadline:
        before, client_rect, result = _capture_for_client(hwnd, adapter)
        if result is not None:
            return result
        point = locate_button_by_template(client_rect, template_path, confidence, frame=before)
        if point is not None:
            break
        time.sleep(0.15)
    if point is None:
        return MenuNavResult.BUTTON_NOT_FOUND
    if not adapter.activate_and_confirm(hwnd):
        return MenuNavResult.FOREGROUND_NOT_CONFIRMED
    if not adapter.send_enter(hwnd):
        return MenuNavResult.WINDOW_LOST if not adapter.is_window(hwnd) else MenuNavResult.WINDOW_NOT_READY
    return wait_for_gameplay_change(hwnd, before_frame=before, adapter=adapter)
