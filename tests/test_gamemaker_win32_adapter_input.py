import ctypes

import pytest

from app.runtime_engines.gamemaker.menu_navigator import Win32WindowAdapter
from app.runtime_engines.gamemaker.win32_input import INPUT, VK_RETURN


class Sender:
    def __init__(self, result):
        self.result, self.calls = result, []

    def __call__(self, count, inputs, cb_size):
        self.calls.append((count, inputs, cb_size))
        return self.result


def _adapter_with_mock(monkeypatch, returned_count, last_error):
    sender = Sender(returned_count)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: type("User32", (), {"SendInput": sender})())
    monkeypatch.setattr(ctypes, "set_last_error", lambda value: None)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: last_error)
    adapter = Win32WindowAdapter()
    monkeypatch.setattr(adapter, "is_window", lambda hwnd: True)
    return adapter, sender


@pytest.mark.parametrize("returned,last_error,expected", [(2, 0, True), (1, 5, False), (0, 87, False)])
def test_send_enter_preserves_mocked_win32_result(monkeypatch, returned, last_error, expected):
    adapter, sender = _adapter_with_mock(monkeypatch, returned, last_error)
    assert adapter.send_enter(7) is expected
    assert adapter.last_sendinput_result["returned_count"] == returned
    assert adapter.last_sendinput_result["last_error"] == last_error
    count, inputs, cb_size = sender.calls[0]
    assert count == 2 and cb_size == ctypes.sizeof(INPUT)
    assert inputs[0].union.ki.wVk == VK_RETURN and inputs[0].union.ki.dwFlags == 0
    assert inputs[1].union.ki.wVk == VK_RETURN and inputs[1].union.ki.dwFlags == 2
