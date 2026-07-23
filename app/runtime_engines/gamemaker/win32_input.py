"""Pure Win32 input-layout helpers; these do not call SendInput."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

INPUT_KEYBOARD = 1
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def build_enter_inputs():
    inputs = (INPUT * 2)()
    inputs[0].type = inputs[1].type = INPUT_KEYBOARD
    inputs[0].union.ki = KEYBDINPUT(VK_RETURN, 0, 0, 0, 0)
    inputs[1].union.ki = KEYBDINPUT(VK_RETURN, 0, KEYEVENTF_KEYUP, 0, 0)
    return inputs


def interpret_sendinput_result(returned_count: int, last_error: int) -> dict[str, int | bool]:
    return {"returned_count": returned_count, "last_error": last_error, "success": returned_count == 2}
