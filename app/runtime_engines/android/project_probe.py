"""Detect Flutter / Kotlin / Java Android projects and APK artifacts."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        "build",
        ".gradle",
        ".dart_tool",
        "Pods",
        ".idea",
    }
)


def _under_skip(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    if "outputs" in parts and "apk" in parts:
        return False
    return any(part.lower() in _SKIP_DIRS for part in path.parts)


def find_apk_artifact(root: Path) -> Optional[Path]:
    if root.is_file() and root.suffix.lower() in {".apk", ".aab"}:
        return root
    if not root.is_dir():
        return None

    candidates: List[Path] = []
    for pattern in ("*.apk", "*.aab"):
        for p in root.rglob(pattern):
            if not p.is_file() or _under_skip(p):
                continue
            if "androidtest" in p.as_posix().lower() or "test" in p.parent.name.lower():
                continue
            candidates.append(p)

    if not candidates:
        return None

    def score_apk(p: Path) -> tuple:
        name = p.name.lower()
        rel = p.as_posix().lower()
        pref = 0
        if "release" in name:
            pref += 3
        elif "debug" in name:
            pref += 2
        if "outputs/apk" in rel:
            pref += 2
        if "flutter" in rel:
            pref += 1
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        return (pref, size)

    candidates.sort(key=score_apk, reverse=True)
    return candidates[0]


def detect_project_stack(root: Path) -> Dict[str, Any]:
    """Classify Android-related submission: Flutter, Kotlin, Java, or APK-only."""
    info: Dict[str, Any] = {
        "platform_type": "none",
        "flutter": False,
        "kotlin": False,
        "java": False,
        "android_gradle": False,
        "apk_path": None,
        "source_files": [],
    }
    if not root.exists():
        return info

    base = root if root.is_dir() else root.parent
    pubspec = base / "pubspec.yaml"
    if not pubspec.is_file():
        for hit in base.rglob("pubspec.yaml"):
            if not _under_skip(hit):
                pubspec = hit
                base = hit.parent
                break

    if pubspec.is_file():
        info["flutter"] = True
        info["platform_type"] = "flutter"

    gradle_files = [
        p
        for p in list(base.rglob("build.gradle")) + list(base.rglob("build.gradle.kts"))
        if not _under_skip(p) and "android" in p.as_posix().lower()
    ]
    if gradle_files:
        info["android_gradle"] = True
        if info["platform_type"] == "none":
            info["platform_type"] = "kotlin"

    kt_files = [p for p in base.rglob("*.kt") if not _under_skip(p)][:20]
    java_files = [p for p in base.rglob("*.java") if not _under_skip(p)][:20]
    if kt_files:
        info["kotlin"] = True
        info["source_files"].extend(str(p) for p in kt_files[:8])
        if info["platform_type"] in ("none", "kotlin"):
            info["platform_type"] = "kotlin"
    if java_files:
        info["java"] = True
        info["source_files"].extend(str(p) for p in java_files[:8])
        if info["platform_type"] == "none":
            info["platform_type"] = "java"

    apk = find_apk_artifact(base)
    if apk:
        info["apk_path"] = str(apk)
        if info["platform_type"] == "none":
            info["platform_type"] = "apk_only"

    return info


def extract_package_name_from_apk(apk: Path) -> Optional[str]:
    if not apk.is_file() or not zipfile.is_zipfile(apk):
        return None
    try:
        with zipfile.ZipFile(apk, "r") as zf:
            if "AndroidManifest.xml" not in {n.lower() for n in zf.namelist()}:
                return None
            raw = zf.read("AndroidManifest.xml")
            m = re.search(rb'package=["\']([^"\']+)["\']', raw)
            if m:
                return m.group(1).decode("utf-8", errors="replace")
    except Exception:
        return None
    return None


def submission_has_android_artifacts(root: Path) -> bool:
    probe = detect_project_stack(root)
    return probe["platform_type"] != "none"
