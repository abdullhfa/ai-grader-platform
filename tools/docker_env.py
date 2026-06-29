"""Resolve Docker CLI on Windows and verify daemon readiness."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

DOCKER_BIN_DIRS = [
    Path(r"C:\Program Files\Docker\Docker\resources\bin"),
    Path(r"C:\Program Files\Docker\cli-plugins"),
]


def ensure_docker_cli() -> bool:
    if shutil.which("docker"):
        return True
    prefix = os.environ.get("PATH", "")
    for directory in DOCKER_BIN_DIRS:
        docker_exe = directory / "docker.exe"
        if docker_exe.is_file() and str(directory) not in prefix:
            os.environ["PATH"] = str(directory) + os.pathsep + prefix
            prefix = os.environ["PATH"]
    return shutil.which("docker") is not None


def docker_daemon_ready() -> bool:
    if not ensure_docker_cli():
        return False
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def wait_for_docker_daemon(timeout_sec: int = 180) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if docker_daemon_ready():
            return True
        time.sleep(5)
    return False
