"""Unity runtime hardening — manifest validation, static fallback, package hints."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from app.runtime_engines.unity.scene_parser import validate_unity_scenes


def validate_unity_manifest(project_root: Path) -> Dict[str, Any]:
    """Package manifest and project structure checks."""
    manifest_path = project_root / "Packages" / "manifest.json"
    result: Dict[str, Any] = {
        "manifest_present": manifest_path.is_file(),
        "package_conflicts": [],
        "warnings": [],
    }
    if not manifest_path.is_file():
        result["warnings"].append("packages_manifest_missing")
        return result

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["valid"] = False
        result["error"] = str(exc)
        return result

    deps = data.get("dependencies") or {}
    result["dependency_count"] = len(deps)
    duplicates = [k for k in deps if k.count(".") > 4]
    if duplicates:
        result["warnings"].append("unusual_package_ids")
    result["valid"] = True
    return result


def analyze_unity_static_project(project_root: Path) -> Dict[str, Any]:
    """Static inference when build/runtime unavailable."""
    scene_report = validate_unity_scenes(project_root)
    manifest_report = validate_unity_manifest(project_root)

    cs_files: List[str] = []
    assets = project_root / "Assets"
    if assets.is_dir():
        for fp in assets.rglob("*.cs"):
            if len(cs_files) >= 30:
                break
            cs_files.append(fp.relative_to(project_root).as_posix())

    version_hint = ""
    version_file = project_root / "ProjectSettings" / "ProjectVersion.txt"
    if version_file.is_file():
        match = re.search(r"m_EditorVersion:\s*(\S+)", version_file.read_text(encoding="utf-8", errors="replace"))
        if match:
            version_hint = match.group(1)

    completeness = 0.35
    if scene_report.get("has_playable_scene"):
        completeness += 0.25
    if manifest_report.get("manifest_present"):
        completeness += 0.15
    if cs_files:
        completeness += 0.15
    if scene_report.get("validation_passed"):
        completeness += 0.10

    return {
        "mode": "unity_static_analysis",
        "scene_validation": scene_report,
        "manifest_validation": manifest_report,
        "script_count": len(cs_files),
        "sample_scripts": cs_files[:8],
        "unity_version_hint": version_hint,
        "completeness_hint": min(1.0, completeness),
        "gameplay_inference": {
            "has_scenes": scene_report.get("scene_count", 0) > 0,
            "has_scripts": len(cs_files) > 0,
            "likely_playable": bool(scene_report.get("has_playable_scene") and cs_files),
        },
    }
