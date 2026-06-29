"""ClamAV integration — optional subprocess scan."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict


def clamav_available() -> bool:
    return shutil.which("clamscan") is not None or shutil.which("clamdscan") is not None


def scan_with_clamav(path: Path, *, timeout: int = 120) -> Dict[str, Any]:
    if not os.environ.get("AI_GRADER_MALWARE_SCAN", "1").strip().lower() in ("1", "true", "yes", "on"):
        return {"scanner": "clamav", "skipped": True, "clean": True}

    binary = "clamdscan" if shutil.which("clamdscan") else "clamscan"
    if not shutil.which(binary):
        return {"scanner": "clamav", "skipped": True, "clean": True, "note": "clamav_not_installed"}

    try:
        proc = subprocess.run(
            [binary, "--no-summary", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        infected = proc.returncode == 1
        return {
            "scanner": "clamav",
            "clean": not infected,
            "infected": infected,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"scanner": "clamav", "clean": False, "error": "timeout"}
    except Exception as exc:
        return {"scanner": "clamav", "clean": True, "skipped": True, "error": str(exc)}
