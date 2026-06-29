"""Locate Scratch .sb3 / .sb2 project files."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def find_scratch_project(root: Path) -> Optional[Path]:
    if root.is_file() and root.suffix.lower() in {".sb3", ".sb2"}:
        return root
    if not root.is_dir():
        return None
    for pattern in ("*.sb3", "*.sb2"):
        for fp in sorted(root.rglob(pattern)):
            if fp.is_file() and "node_modules" not in fp.parts:
                return fp
    return None


def detect_scratch_confidence(root: Path) -> float:
    sb3 = find_scratch_project(root)
    if not sb3:
        return 0.0
    if sb3.suffix.lower() == ".sb3":
        return 0.93
    return 0.88


def load_scratch_project_json(sb3_path: Path) -> Dict[str, Any]:
    """Load project.json from .sb3 (zip) or legacy .sb2."""
    if not sb3_path.is_file():
        return {"ok": False, "error": "file_missing"}

    if sb3_path.suffix.lower() == ".sb3":
        try:
            with zipfile.ZipFile(sb3_path, "r") as zf:
                if "project.json" not in zf.namelist():
                    return {"ok": False, "error": "project_json_missing"}
                data = zf.read("project.json").decode("utf-8")
            import json

            project = json.loads(data)
            return {"ok": True, "project": project, "format": "sb3", "path": str(sb3_path)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    try:
        import json

        project = json.loads(sb3_path.read_text(encoding="utf-8"))
        return {"ok": True, "project": project, "format": "sb2", "path": str(sb3_path)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
