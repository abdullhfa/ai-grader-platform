"""Unity project and build detection — Sprint 2.1/2.2."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from app.runtime_engines.unity.models import UnityDetectionResult


def find_unity_project_root(root: Path) -> Optional[Path]:
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        return None

    direct_settings = root / "ProjectSettings" / "ProjectVersion.txt"
    if direct_settings.is_file() and (root / "Assets").is_dir():
        return root

    for candidate in root.rglob("ProjectSettings"):
        if not candidate.is_dir():
            continue
        project_root = candidate.parent
        if (project_root / "Assets").is_dir():
            return project_root
    return None


def read_unity_version(project_root: Path) -> str:
    version_file = project_root / "ProjectSettings" / "ProjectVersion.txt"
    if not version_file.is_file():
        return ""
    try:
        text = version_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = re.search(r"m_EditorVersion:\s*(\S+)", text)
    return match.group(1) if match else ""


def find_unity_executable(root: Path) -> Optional[Path]:
    search_root = root if root.is_dir() else root.parent
    candidates: List[Path] = []
    for fp in search_root.rglob("*.exe"):
        if "unitycrashhandler" in fp.name.lower():
            continue
        try:
            from app.runtime_observation_sandbox import detect_unity_build_for_exe

            if detect_unity_build_for_exe(fp).get("detected"):
                candidates.append(fp)
        except Exception:
            data_dir = fp.parent / f"{fp.stem}_Data"
            if data_dir.is_dir():
                candidates.append(fp)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.parts), p.name.lower() != "game.exe", p.name))
    return candidates[0]


def detect_unity_layout(root: Path) -> UnityDetectionResult:
    project_root = find_unity_project_root(root)
    executable = find_unity_executable(root)
    scenes: List[str] = []
    if project_root:
        from app.runtime_engines.unity.scene_parser import list_unity_scenes

        scenes = list_unity_scenes(project_root)

    build_confidence = "none"
    if executable:
        try:
            from app.runtime_observation_sandbox import detect_unity_build_for_exe

            build_confidence = str(detect_unity_build_for_exe(executable).get("confidence") or "medium")
        except Exception:
            build_confidence = "medium"

    return UnityDetectionResult(
        project_root=project_root,
        executable=executable,
        unity_version=read_unity_version(project_root) if project_root else "",
        scene_paths=scenes,
        has_source_project=project_root is not None,
        has_build_executable=executable is not None,
        build_confidence=build_confidence,
    )


def detect_confidence(root: Path) -> float:
    result = detect_unity_layout(root)
    if result.has_build_executable:
        return 0.95
    if result.has_source_project:
        return 0.82
    return 0.0


# Backward compatibility alias
def probe_unity_layout(root: Path) -> dict:
    return detect_unity_layout(root).to_dict()
