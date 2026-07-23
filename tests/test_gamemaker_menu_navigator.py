from __future__ import annotations

import ast
import inspect

from pathlib import Path

import numpy as np
from PIL import Image

from app.runtime_engines.gamemaker.menu_navigator import MenuNavResult, WindowAdapter, navigate_menu_deterministic


class FakeWindow:
    def __init__(self, frames, *, exists=True, rect=(10, 20, 210, 120), client_rect=None, click_ok=True):
        self.frames = list(frames)
        self.exists = exists
        self.rect = rect
        self.client_rect = client_rect or rect
        self.click_ok = click_ok
        self.clicks = []
        self.enter_calls = []
        self.foreground = True
        self.activation_calls = 0

    def is_window(self, hwnd):
        return self.exists

    def get_rect(self, hwnd):
        return self.rect if self.exists else None

    def get_client_rect(self, hwnd):
        return self.client_rect if self.exists else None

    def capture(self, hwnd):
        if not self.exists:
            return None
        if not self.frames:
            return None
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    def activate_and_confirm(self, hwnd):
        return self.foreground

    def send_enter(self, hwnd):
        self.enter_calls.append(hwnd)
        return True
    def click_client(self, hwnd, point):
        self.clicks.append((hwnd, point))
        return self.click_ok


def _template(tmp_path: Path):
    array = np.zeros((30, 80, 3), dtype=np.uint8)
    array[:, :] = (20, 180, 30)
    array[4:8, 5:75] = (245, 245, 245)
    path = tmp_path / "easy.png"
    Image.fromarray(array).save(path)
    return path, array


def _menu(template):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[35:65, 60:140] = template
    return frame


def test_window_adapter_protocol_has_signatures_only():
    tree = ast.parse(inspect.getsource(WindowAdapter))
    protocol = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    for method in (node for node in protocol.body if isinstance(node, ast.FunctionDef)):
        executable = [statement for statement in method.body if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and statement.value.value is Ellipsis)]
        assert executable == [], method.name

def test_gameplay_entered_after_template_click(tmp_path):
    path, template = _template(tmp_path)
    menu, gameplay = _menu(template), np.full((100, 200, 3), 255, dtype=np.uint8)
    fake = FakeWindow([menu, menu, menu, gameplay])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.GAMEPLAY_ENTERED
    assert fake.enter_calls == [7]


def test_waits_for_menu_template_after_splash(tmp_path):
    path, template = _template(tmp_path)
    splash = np.full((100, 200, 3), 80, dtype=np.uint8)
    menu = _menu(template)
    gameplay = np.full((100, 200, 3), 255, dtype=np.uint8)
    fake = FakeWindow([splash, splash, splash, menu, gameplay])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, menu_timeout_s=1, adapter=fake) is MenuNavResult.GAMEPLAY_ENTERED

def test_readiness_failure_blocks_foreground_and_enter(tmp_path):
    path, _ = _template(tmp_path)
    fake = FakeWindow([])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.WINDOW_LOST
    assert fake.activation_calls == 0
    assert fake.enter_calls == []

def test_rejects_keyboard_input_without_foreground(tmp_path):
    path, template = _template(tmp_path)
    menu = _menu(template)
    fake = FakeWindow([menu, menu, menu])
    fake.foreground = False
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.FOREGROUND_NOT_CONFIRMED
    assert fake.enter_calls == []

def test_button_not_found(tmp_path):
    path, _ = _template(tmp_path)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    fake = FakeWindow([frame, frame, frame])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.BUTTON_NOT_FOUND


def test_capture_dimensions_match_hwnd_client_rect(tmp_path):
    path, template = _template(tmp_path)
    frame = _menu(template)
    fake = FakeWindow([frame, frame], client_rect=(10, 20, 210, 121))
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.CAPTURE_DIMENSION_MISMATCH
    assert fake.clicks == []

def test_window_not_ready_when_geometry_changes(tmp_path):
    path, template = _template(tmp_path)
    fake = FakeWindow([_menu(template)])
    assert navigate_menu_deterministic(7, (0, 0, 1, 1), template_path=path, adapter=fake) is MenuNavResult.WINDOW_NOT_READY


def test_window_lost_before_navigation(tmp_path):
    path, _ = _template(tmp_path)
    fake = FakeWindow([], exists=False)
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.WINDOW_LOST


def test_no_scene_change_detected(tmp_path):
    path, template = _template(tmp_path)
    menu = _menu(template)
    fake = FakeWindow([menu, menu, menu, menu])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.NO_SCENE_CHANGE_DETECTED
