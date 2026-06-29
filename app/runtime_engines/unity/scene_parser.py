"""Unity scene parsing and build-settings validation — Sprint 2.2."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from app.runtime_engines.unity.detector import find_unity_project_root


def list_unity_scenes(project_root: Path) -> List[str]:
    scenes: List[str] = []
    build_settings = project_root / "ProjectSettings" / "EditorBuildSettings.asset"
    if build_settings.is_file():
        try:
            text = build_settings.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for match in re.finditer(r"path:\s*(Assets/[^\n\r]+\.unity)", text):
            scenes.append(match.group(1).strip())

    assets = project_root / "Assets"
    if assets.is_dir():
        for fp in assets.rglob("*.unity"):
            rel = fp.relative_to(project_root).as_posix()
            if rel not in scenes:
                scenes.append(rel)
    return scenes[:40]


def parse_scene_manifest(project_root: Path) -> Dict[str, Any]:
    scenes = list_unity_scenes(project_root)
    present: List[str] = []
    missing: List[str] = []
    for rel in scenes:
        full = project_root / Path(rel.replace("\\", "/"))
        if full.is_file():
            present.append(rel)
        else:
            missing.append(rel)

    packages_lock = project_root / "Packages" / "manifest.json"
    return {
        "scene_count": len(scenes),
        "scenes_present": present,
        "scenes_missing": missing,
        "build_settings_scene_count": len([s for s in scenes if s.startswith("Assets/")]),
        "validation_passed": len(scenes) > 0 and not missing,
        "has_playable_scene": len(present) > 0,
        "packages_manifest_present": packages_lock.is_file(),
    }


def validate_unity_scenes(project_root: Path) -> Dict[str, Any]:
    return parse_scene_manifest(project_root)
