import ctypes

from app.runtime_engines.gamemaker.win32_input import (
    HARDWAREINPUT, INPUT, INPUT_KEYBOARD, INPUT_UNION, KEYBDINPUT,
    KEYEVENTF_KEYUP, MOUSEINPUT, VK_RETURN, build_enter_inputs,
    interpret_sendinput_result,
)


def test_win64_input_layout_and_union_members():
    assert ctypes.sizeof(INPUT) == 40
    assert {name for name, _ in INPUT_UNION._fields_} == {"mi", "ki", "hi"}
    assert MOUSEINPUT and KEYBDINPUT and HARDWAREINPUT


def test_enter_input_array_has_keydown_then_keyup_and_matching_cbsize():
    inputs = build_enter_inputs()
    assert len(inputs) == 2
    assert ctypes.sizeof(INPUT) == 40
    assert inputs[0].type == inputs[1].type == INPUT_KEYBOARD
    assert inputs[0].union.ki.wVk == inputs[1].union.ki.wVk == VK_RETURN
    assert inputs[0].union.ki.dwFlags == 0
    assert inputs[1].union.ki.dwFlags == KEYEVENTF_KEYUP


def test_sendinput_return_counts_preserve_numeric_result_and_error():
    assert interpret_sendinput_result(2, 0) == {"returned_count": 2, "last_error": 0, "success": True}
    assert interpret_sendinput_result(1, 5) == {"returned_count": 1, "last_error": 5, "success": False}
    assert interpret_sendinput_result(0, 87) == {"returned_count": 0, "last_error": 87, "success": False}
