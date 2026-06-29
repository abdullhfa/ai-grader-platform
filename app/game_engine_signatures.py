"""
Single source of truth for game-engine + runnable-game file signatures.

Historically these lists were duplicated across at least four modules
(artifact_inventory, evidence_completeness_gate, btec_criteria_governance,
preflight_evidence_scan). A fix applied to one path (e.g. adding Scratch ``.sb3``)
silently missed the others, causing valid submissions to be graded ``U``. All paths
now import from here so a new engine/extension is added exactly once.

Pure data + tiny pure helpers — no I/O, deterministic, trivially testable.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

# --- Project / source signatures per engine -------------------------------------
GAMEMAKER_PROJECT_EXTENSIONS = frozenset({".yyp", ".yy", ".gml", ".yyz"})
GAMEMAKER_BUILD_FILENAMES = frozenset({"data.win"})
# Scratch projects are self-contained, runnable games (not just source).
SCRATCH_PROJECT_EXTENSIONS = frozenset({".sb3", ".sb2", ".sb"})

# Substring markers used for fast, path-name-only engine detection (lower-cased).
ENGINE_PATH_MARKERS: Dict[str, Tuple[str, ...]] = {
    "godot": ("project.godot", ".gd", ".tscn", ".pck"),
    "unity": ("assets/", "projectsettings/", ".unity"),
    "gamemaker": (".yyp", ".yy", ".yyz", ".gml", ".win"),
    "unreal": (".uproject", "content/", "binaries/"),
    "scratch": (".sb3", ".sb2", ".sb"),
}

# Tokens that, on their own, signal "a runnable/sourced game project exists".
PROJECT_MARKER_TOKENS: Tuple[str, ...] = (
    "project.godot",
    ".yyp",
    ".yy",
    ".yyz",
    ".uproject",
    "assets/",
    ".sb3",
    ".sb2",
    ".sb",
)

# Runnable deliverables that count as an executable-equivalent build, even without
# a classic .exe (closed/Linux/web engines). Project-as-build (Scratch) + GameMaker
# runtime data file.
RUNNABLE_GAME_EXTENSIONS = frozenset({".sb3", ".sb2"})
RUNNABLE_GAME_FILENAMES = frozenset({"data.win"})

# Classic executable / packaged-build extensions.
EXECUTABLE_BUILD_EXTENSIONS = frozenset({".exe", ".win", ".pck", ".apk", ".aab", ".app"})


def detect_engine_from_text(joined_lower: str) -> Optional[str]:
    """Return the first engine whose markers appear in the lower-cased path blob."""
    if not joined_lower:
        return None
    for engine, markers in ENGINE_PATH_MARKERS.items():
        if any(m in joined_lower for m in markers):
            return engine
    return None


def has_runnable_game_project(joined_lower: str) -> bool:
    """True if any project/runnable marker is present in the path blob."""
    if not joined_lower:
        return False
    return any(tok in joined_lower for tok in PROJECT_MARKER_TOKENS)


def is_runnable_game_path(name_lower: str, ext_lower: str) -> bool:
    """True if a single file is a runnable-game deliverable (Scratch project / data.win)."""
    return name_lower in RUNNABLE_GAME_FILENAMES or ext_lower in RUNNABLE_GAME_EXTENSIONS


def paths_contain_runnable_game(paths: Sequence[str]) -> bool:
    from pathlib import PurePosixPath

    for raw in paths or []:
        p = PurePosixPath((raw or "").replace("\\", "/"))
        if is_runnable_game_path(p.name.lower(), p.suffix.lower()):
            return True
    return False
