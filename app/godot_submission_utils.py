"""Shared Godot submission path helpers — intake, inventory, coverage."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence

# Path segments / fragments for vendor Godot editor bundles inside student zips.
_GODOT_EDITOR_PATH_FRAGMENTS = (
    "godot_v4.",
    "godot_v3.",
    "godot.windows",
    "godot.mono",
    "أدوات التصدير",
    "export templates",
    "editor_data",
    "/modules/",
    "\\modules\\",
    "mono_glue",
    "thirdparty",
)

_GODOT_EDITOR_CS_RE = re.compile(
    r"(?:^|[/\\])modules[/\\]|(?:^|[/\\])editor[/\\]|godot[/\\]core[/\\]",
    re.IGNORECASE,
)


def is_godot_editor_bundle_path(path: Path | str) -> bool:
    """True when a path is inside a shipped Godot Engine editor/template tree."""
    lower = str(path).replace("\\", "/").lower()
    if any(frag in lower for frag in _GODOT_EDITOR_PATH_FRAGMENTS):
        return True
    if _GODOT_EDITOR_CS_RE.search(lower):
        return True
    try:
        from app.runtime_engines.godot.export_runner import is_godot_editor_executable

        p = Path(path)
        if p.suffix.lower() in {".exe", ".x86_64"} and is_godot_editor_executable(p):
            return True
    except Exception:
        pass
    return False


def should_skip_grading_path(path: Path | str) -> bool:
    """Skip engine bundles and build noise when expanding submission trees."""
    if is_godot_editor_bundle_path(path):
        return True
    lower = str(path).replace("\\", "/").lower()
    skip_dirs = (
        "/library/", "\\library\\",
        "/.godot/", "\\.godot\\",
        "/.import/", "\\.import\\",
        "/monobleedingedge/", "\\monobleedingedge\\",
        "/embedruntime/", "\\embedruntime\\",
        "/node_modules/", "\\node_modules\\",
    )
    return any(seg in lower for seg in skip_dirs)


def find_godot_submission_root(
    primary_path: str,
    *,
    student_name: str = "",
) -> Path:
    """Resolve the student folder for Godot/game builds (exe/pck/project.godot)."""
    p = Path(primary_path)
    try:
        p = p.resolve()
    except OSError:
        p = Path(primary_path)
    if not p.exists():
        return p.parent if p.suffix else p

    start = p.parent if p.is_file() else p
    name_key = (student_name or "").strip().casefold()

    def _name_matches(folder: Path) -> bool:
        if not name_key:
            return False
        return folder.name.casefold() == name_key or name_key in folder.name.casefold()

    def _score_folder(folder: Path) -> int:
        if not folder.is_dir():
            return -10_000
        score = 0
        if _name_matches(folder):
            score += 200
        try:
            for child in folder.iterdir():
                if not child.is_file():
                    continue
                ext = child.suffix.lower()
                if ext in {".exe", ".apk", ".pck"}:
                    score += 40
                if child.name.lower() == "project.godot":
                    score += 80
                if ext in {".gd", ".gml", ".yyp"}:
                    score += 25
        except OSError:
            pass
        return score

    best = start
    best_score = _score_folder(start)
    for candidate in [start, *list(start.parents)[:4]]:
        sc = _score_folder(candidate)
        if sc > best_score:
            best_score = sc
            best = candidate
        if _name_matches(candidate) and sc >= best_score:
            return candidate
    return best
