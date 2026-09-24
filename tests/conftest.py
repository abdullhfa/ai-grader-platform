"""Suite-wide test defaults."""
from __future__ import annotations

import os


def _force_no_gamemaker_install_wait() -> None:
    # .env may set a long production grace window (e.g. 3600). Never block the suite.
    os.environ["AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS"] = "0"


_force_no_gamemaker_install_wait()


def pytest_configure(config) -> None:  # noqa: ARG001
    _force_no_gamemaker_install_wait()
