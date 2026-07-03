"""PRO capture metadata — requirement_id / phase on capture_runtime_screenshot."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime_observation_sandbox import capture_runtime_screenshot


def test_capture_accepts_requirement_id_and_phase_without_type_error():
    """PlaytestOrchestrator passes PRO metadata; must not crash on signature mismatch."""
    fake_image = MagicMock()
    fake_image.width = 100
    fake_image.height = 80

    with patch("app.runtime_observation_sandbox.sys.platform", "linux"):
        shot = capture_runtime_screenshot(
            Path("game.exe"),
            label="req_player_movement_pre",
            elapsed_seconds=1.0,
            requirement_id="player_movement",
            phase="pre",
            extra_future_key="ignored",
        )
    assert shot["requirement_id"] == "player_movement"
    assert shot["phase"] == "pre"
    assert shot["errors"]  # windows-only path on linux mock
