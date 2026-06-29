"""GameMaker runtime log parsing — player/output logs when present."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


_ERROR_PATTERNS = (
    re.compile(r"ERROR\s*:\s*(.+)", re.I),
    re.compile(r"FATAL\s*:\s*(.+)", re.I),
    re.compile(r"Unable to find any compatible Direct3D devices", re.I),
    re.compile(r"GameMaker Studio", re.I),
)


def parse_gamemaker_log_text(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    errors: List[str] = []
    crash_signals = 0
    for line in lines:
        for pat in _ERROR_PATTERNS:
            if pat.search(line):
                errors.append(line.strip()[:500])
                if "fatal" in line.lower() or "unable" in line.lower():
                    crash_signals += 1
                break
    return {
        "line_count": len(lines),
        "error_lines": errors[:20],
        "crash_signal_count": crash_signals,
        "gamemaker_log_detected": any("gamemaker" in ln.lower() for ln in lines[:50]),
    }


def parse_gamemaker_log_file(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    parsed = parse_gamemaker_log_text(text)
    parsed["ok"] = True
    parsed["path"] = str(path)
    return parsed
