from __future__ import annotations

from types import SimpleNamespace

from PIL import Image


def test_focus_uses_kernel32_current_thread_id(monkeypatch):
    """Regression: GameMaker focus must not abort on a user32 symbol lookup."""
    from app import window_focus_manager as manager

    target_hwnd = 123

    class FakeKernel32:
        def __init__(self) -> None:
            self.calls = 0

        def GetCurrentThreadId(self) -> int:
            self.calls += 1
            return 100

    class FakeUser32:
        def __init__(self) -> None:
            self.foreground = 999
            self.set_foreground_calls = 0
            self.set_window_pos_calls = 0

        def IsWindow(self, _hwnd):
            return True

        def ShowWindow(self, _hwnd, _mode):
            return True

        def BringWindowToTop(self, _hwnd):
            return True

        def SetWindowPos(self, *_args):
            self.set_window_pos_calls += 1
            return True

        def SetForegroundWindow(self, hwnd):
            self.set_foreground_calls += 1
            if self.set_foreground_calls >= 2:
                self.foreground = hwnd
            return True

        def GetForegroundWindow(self):
            return self.foreground

        def SwitchToThisWindow(self, _hwnd, _alt_tab):
            return True

        def GetWindowThreadProcessId(self, hwnd, _pid):
            return 300 if hwnd == target_hwnd else 200

        def AttachThreadInput(self, _source, _target, _attach):
            return True

        def SetActiveWindow(self, _hwnd):
            return True

        def SetFocus(self, _hwnd):
            return target_hwnd

    kernel32 = FakeKernel32()
    user32 = FakeUser32()
    monkeypatch.setattr(
        manager.ctypes,
        "windll",
        SimpleNamespace(user32=user32, kernel32=kernel32),
    )
    monkeypatch.setattr(
        manager,
        "_enum_windows",
        lambda **_kwargs: [
            {"hwnd": target_hwnd, "title": "CheeseChase", "bbox": (10, 20, 650, 500)}
        ],
    )

    assert manager.focus_game_window(process_pid=42) is True
    assert kernel32.calls == 1
    assert user32.set_window_pos_calls == 1
    assert user32.GetForegroundWindow() == target_hwnd


def test_direct_capture_uses_window_surface_even_without_pywin32(monkeypatch):
    from app import window_focus_manager as manager

    expected = Image.new("RGB", (640, 480), "gold")
    monkeypatch.setattr(
        manager,
        "_resolve_game_window_row",
        lambda **_kwargs: {
            "hwnd": 321,
            "title": "CheeseChase",
            "bbox": (10, 20, 650, 500),
        },
    )
    monkeypatch.setattr(
        manager,
        "_capture_window_surface",
        lambda hwnd, width, height: expected
        if (hwnd, width, height) == (321, 640, 480)
        else None,
    )

    result = manager.capture_game_window_image(
        artifact_path=manager.Path("CheeseChase.exe"),
        process_pid=42,
    )

    assert result is not None
    assert result["image"] is expected
    assert result["bbox"] == (10, 20, 650, 500)
    assert result["method"] == "win32_printwindow_ctypes"


def test_window_protection_restores_and_disables_user_close_or_minimize(monkeypatch):
    from app import window_focus_manager as manager

    class FakeUser32:
        def __init__(self) -> None:
            self.show_modes = []
            self.menu_commands = []
            self.window_pos = []
            self.style = 0x00020000

        def IsIconic(self, _hwnd):
            return True

        def IsWindowVisible(self, _hwnd):
            return False

        def ShowWindow(self, _hwnd, mode):
            self.show_modes.append(mode)
            return True

        def GetWindowRect(self, _hwnd, rect_ptr):
            rect = rect_ptr._obj
            rect.left, rect.top, rect.right, rect.bottom = 10, 20, 650, 500
            return True

        def GetSystemMenu(self, _hwnd, _revert):
            return 77

        def EnableMenuItem(self, _menu, command, _flags):
            self.menu_commands.append(command)
            return True

        def GetWindowLongW(self, _hwnd, _index):
            return self.style

        def SetWindowLongW(self, _hwnd, _index, style):
            self.style = style
            return style

        def SetWindowPos(self, *args):
            self.window_pos.append(args)
            return True

        def DrawMenuBar(self, _hwnd):
            return True

    user32 = FakeUser32()
    monkeypatch.setattr(manager.sys, "platform", "win32")
    monkeypatch.setattr(
        manager.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
    )
    monkeypatch.setattr(
        manager,
        "_resolve_game_window_row",
        lambda **_kwargs: {
            "hwnd": 321,
            "title": "CheeseChase",
            "bbox": (10, 20, 650, 500),
        },
    )
    manager._WINDOW_RECT_CACHE[42] = (10, 20, 650, 500)

    state = manager.protect_game_window(process_pid=42)

    assert state["window_found"] is True
    assert state["restored"] is True
    assert state["close_disabled"] is True
    assert state["minimize_disabled"] is True
    assert state["topmost"] is True
    assert user32.show_modes == [9]
    assert user32.menu_commands == [0xF060, 0xF020]
    assert user32.style & 0x00020000 == 0
    assert user32.window_pos


def test_runtime_window_protector_records_recovery(monkeypatch):
    from app import window_focus_manager as manager

    monkeypatch.setattr(
        manager,
        "protect_game_window",
        lambda **_kwargs: {
            "window_found": True,
            "restored": True,
            "geometry_restored": True,
            "close_disabled": True,
            "minimize_disabled": True,
            "topmost": True,
        },
    )

    protector = manager.RuntimeWindowProtector(
        42,
        interval_seconds=10,
        enable_input_guard=False,
    ).start()
    report = protector.stop()

    assert report["monitor_ticks"] >= 1
    assert report["window_detected"] is True
    assert report["restore_count"] >= 1
    assert report["geometry_restore_count"] >= 1
    assert report["close_disabled"] is True
    assert report["minimize_disabled"] is True
    assert report["topmost_applied"] is True


def test_alt_f4_guard_is_scoped_to_the_game_foreground_window():
    from app import window_focus_manager as manager

    manager._WINDOW_HANDLE_CACHE[42] = 321
    protector = manager.RuntimeWindowProtector(42, enable_input_guard=False)

    assert protector._should_block_alt_f4(0x73, 0x20, 321) is True
    assert protector._should_block_alt_f4(0x73, 0x20, 999) is False
    assert protector._should_block_alt_f4(0x73, 0x00, 321) is False
    assert protector._should_block_alt_f4(0x41, 0x20, 321) is False


def test_window_protection_restores_cached_geometry_when_current_rect_is_invalid(
    monkeypatch,
):
    from app import window_focus_manager as manager

    class FakeUser32:
        def __init__(self) -> None:
            self.window_pos = []
            self.current_rect = [-2000, -2000, -1880, -1920]

        def IsWindow(self, _hwnd):
            return True

        def IsIconic(self, _hwnd):
            return False

        def IsWindowVisible(self, _hwnd):
            return True

        def ShowWindow(self, _hwnd, _mode):
            return True

        def GetWindowRect(self, _hwnd, rect_ptr):
            rect = rect_ptr._obj
            rect.left, rect.top, rect.right, rect.bottom = self.current_rect
            return True

        def MoveWindow(self, _hwnd, left, top, width, height, _repaint):
            self.current_rect = [left, top, left + width, top + height]
            return True

        def GetSystemMenu(self, _hwnd, _revert):
            return 77

        def EnableMenuItem(self, *_args):
            return True

        def GetWindowLongW(self, _hwnd, _index):
            return 0

        def SetWindowPos(self, *args):
            self.window_pos.append(args)
            return True

        def DrawMenuBar(self, _hwnd):
            return True

    user32 = FakeUser32()
    monkeypatch.setattr(manager.sys, "platform", "win32")
    monkeypatch.setattr(
        manager.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
    )
    monkeypatch.setattr(manager, "_resolve_game_window_row", lambda **_kwargs: None)
    manager._WINDOW_HANDLE_CACHE[42] = 321
    manager._WINDOW_RECT_CACHE[42] = (10, 20, 650, 500)

    state = manager.protect_game_window(
        process_pid=42,
        artifact_path=manager.Path("CheeseChase.exe"),
    )

    assert state["window_found"] is True
    assert state["geometry_restored"] is True
    assert user32.current_rect == [10, 20, 650, 500]


def test_requirement_playtest_can_promote_stale_menu_navigation_result(
    tmp_path, monkeypatch
):
    from app import gameplay_verifier as verifier

    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "data.win").write_bytes(b"runner")
    stale_navigation = verifier.MenuNavigationResult(
        status="unknown",
        attempts=3,
        gameplay_entered=False,
    )
    package = verifier.EvidencePackage(
        submission_id="jana",
        gameplay_entered=True,
        results=[
            verifier.RequirementResult("menu_navigation", True, confidence=0.9),
            verifier.RequirementResult("player_movement", True, confidence=0.8),
        ],
    )
    monkeypatch.setattr(
        verifier.MenuNavigator,
        "navigate_to_gameplay",
        lambda *_args, **_kwargs: stale_navigation,
    )
    monkeypatch.setattr(
        verifier.PlaytestOrchestrator,
        "run",
        lambda *_args, **_kwargs: package,
    )

    report = verifier.run_automated_gameplay_verification(
        artifact_path=exe,
        process_pid=42,
        capture_screenshot=lambda *_args, **_kwargs: {},
        elapsed_seconds=2.0,
        engine_id="gamemaker",
    )

    assert report["menu_navigation"]["gameplay_entered"] is False
    assert report["evidence_package"]["gameplay_entered"] is True
    assert report["gameplay_entered"] is True
    assert report["player_movement_verified"] is True
    assert report["mechanics_verified_count"] == 1
    assert report["l4_level"] == "L4_partial"
    assert "failure_reason_code" not in report
