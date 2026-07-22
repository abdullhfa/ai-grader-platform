from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.runtime_engines.gamemaker.menu_navigator import MenuNavResult, navigate_menu_deterministic


class FakeWindow:
    def __init__(self, frames, *, exists=True, rect=(10, 20, 210, 120), click_ok=True):
        self.frames = list(frames)
        self.exists = exists
        self.rect = rect
        self.click_ok = click_ok
        self.clicks = []

    def is_window(self, hwnd):
        return self.exists

    def get_rect(self, hwnd):
        return self.rect if self.exists else None

    def capture(self, hwnd):
        if not self.exists:
            return None
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

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


def test_gameplay_entered_after_template_click(tmp_path):
    path, template = _template(tmp_path)
    menu, gameplay = _menu(template), np.full((100, 200, 3), 255, dtype=np.uint8)
    fake = FakeWindow([menu, menu, menu, gameplay])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.GAMEPLAY_ENTERED
    assert fake.clicks == [(7, (110, 70))]


def test_button_not_found(tmp_path):
    path, _ = _template(tmp_path)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    fake = FakeWindow([frame, frame, frame])
    assert navigate_menu_deterministic(7, fake.rect, template_path=path, adapter=fake) is MenuNavResult.BUTTON_NOT_FOUND


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
