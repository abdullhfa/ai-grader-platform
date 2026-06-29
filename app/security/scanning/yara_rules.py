"""YARA-style suspicious pattern detection — heuristic fallback."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

SUSPICIOUS_PATTERNS: List[tuple[str, re.Pattern[bytes]]] = [
    ("powershell_invoke", re.compile(rb"Invoke-(Expression|WebRequest|Shellcode)", re.I)),
    ("cmd_exe", re.compile(rb"\bcmd\.exe\b", re.I)),
    ("base64_blob", re.compile(rb"[A-Za-z0-9+/]{200,}={0,2}")),
    ("eval_js", re.compile(rb"\beval\s*\(", re.I)),
    ("registry_persist", re.compile(rb"HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", re.I)),
]


def scan_file_patterns(path: Path, *, max_bytes: int = 2_000_000) -> Dict[str, Any]:
    matches: List[str] = []
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError as exc:
        return {"scanner": "yara_heuristic", "clean": False, "error": str(exc), "matches": []}

    for name, pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(data):
            matches.append(name)

    return {
        "scanner": "yara_heuristic",
        "clean": len(matches) == 0,
        "matches": matches,
        "flagged": len(matches) > 0,
    }
