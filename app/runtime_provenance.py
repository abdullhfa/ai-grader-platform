"""Source / build provenance for every runtime run.

Every runtime evidence record says *which source* and *which build* produced it,
and *which run* observed it, so V1 and V2 can be compared without one silently
standing in for the other:

  source_provenance   what the project source was (content hash of the source tree)
  build_provenance    what was actually launched (exe/pck identity + hash, who built it)
  runtime_identity    which run (session id, engine, launcher, timestamps, status)
  mismatches          source and build that do not belong together

Nothing here decides a criterion.  A provenance mismatch never hides a runtime
failure, and never turns a blocked run into a verdict.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "runtime_provenance_v1"
MAX_HASH_BYTES = 512 * 1024 * 1024
_MAX_TREE_FILES = 4000
_STALE_BUILD_TOLERANCE_S = 60

MISMATCH_DIFFERENT_VERSION_FOLDER = "build_from_different_version_folder"
MISMATCH_SOURCE_NEWER = "source_newer_than_build"

# Criteria a runtime run is evidence for (BTEC Unit 8 runtime-gated criteria).
RUNTIME_CRITERIA = ("C.P5", "C.P6", "C.M3", "BC.D3")


def _sha256(path: Path) -> Dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError:
        return {"sha256": None, "hash_skipped": "unreadable"}
    if size > MAX_HASH_BYTES:
        return {"sha256": None, "hash_skipped": f"larger_than_{MAX_HASH_BYTES}_bytes"}
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return {"sha256": None, "hash_skipped": "unreadable"}
    return {"sha256": h.hexdigest()}


def file_identity(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Artifact/executable identity: name, size, mtime and content hash."""
    if not path:
        return None
    path = Path(path)
    try:
        st = path.stat()
    except OSError:
        return {"path": str(path), "name": path.name, "exists": False}
    return {
        "path": str(path),
        "name": path.name,
        "exists": True,
        "size_bytes": st.st_size,
        "mtime": int(st.st_mtime),
        **_sha256(path),
    }


def engine_version(engine: str, project_root: Optional[Path]) -> Optional[str]:
    """Engine version recorded in the project source, when available."""
    if not project_root:
        return None
    root = Path(project_root)
    try:
        if engine == "unity":
            text = (root / "ProjectSettings" / "ProjectVersion.txt").read_text("utf-8", "replace")
            m = re.search(r"m_EditorVersion:\s*(\S+)", text)
            return m.group(1) if m else None
        if engine == "godot":
            text = (root / "project.godot").read_text("utf-8", "replace")
            m = re.search(r'config/features=PackedStringArray\("(\d+(?:\.\d+)*)"', text)
            return m.group(1) if m else None
        if engine == "gamemaker":
            for yyp in list(root.glob("*.yyp"))[:1]:
                text = yyp.read_text("utf-8", "replace")
                m = re.search(r'"IDEVersion"\s*:\s*"([^"]+)"', text)
                return m.group(1) if m else None
        if engine == "scratch":
            return None
    except OSError:
        return None
    return None


def source_tree_hash(base: Path) -> Dict[str, Any]:
    """Content hash of the source tree (paths + file hashes of the diff-relevant files)."""
    from app.version_code_diff import _is_candidate, _iter_files

    base = Path(base)
    if not base.is_dir():
        return {"tree_hash": None, "file_count": 0, "newest_mtime": None}
    h = hashlib.sha256()
    count = 0
    newest = 0
    for f in sorted(_iter_files(base)):
        if not _is_candidate(f):
            continue
        if count >= _MAX_TREE_FILES:
            break
        try:
            newest = max(newest, int(f.stat().st_mtime))
        except OSError:
            continue
        digest = _sha256(f).get("sha256") or "unhashed"
        h.update(f"{f.relative_to(base).as_posix()}|{digest}\n".encode())
        count += 1
    return {
        "tree_hash": h.hexdigest() if count else None,
        "file_count": count,
        "newest_mtime": newest or None,
    }


def source_provenance(engine: str, project_root: Optional[Path]) -> Dict[str, Any]:
    if not project_root or not Path(project_root).is_dir():
        return {"available": False, "reason": "no_source_project"}
    tree = source_tree_hash(Path(project_root))
    return {
        "available": bool(tree["tree_hash"]),
        "root": str(project_root),
        "engine_version": engine_version(engine, Path(project_root)),
        **tree,
    }


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def detect_mismatches(
    source: Dict[str, Any],
    build: Dict[str, Any],
    *,
    group_root: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """Source and build that do not belong together.  Platform builds match by construction."""
    found: List[Dict[str, str]] = []
    exe = (build or {}).get("executable") or {}
    if (build or {}).get("kind") != "student_supplied" or not exe.get("exists"):
        return found
    if group_root and exe.get("path") and not _within(Path(exe["path"]), Path(group_root)):
        found.append({
            "code": MISMATCH_DIFFERENT_VERSION_FOLDER,
            "detail": f"build {exe['path']} is outside the version folder {group_root}",
        })
    newest = (source or {}).get("newest_mtime")
    if newest and exe.get("mtime") and newest > int(exe["mtime"]) + _STALE_BUILD_TOLERANCE_S:
        found.append({
            "code": MISMATCH_SOURCE_NEWER,
            "detail": "source files were modified after the build was produced",
        })
    return found


def _find_key(obj: Any, key: str, depth: int = 0) -> Any:
    if depth > 6:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get(key), (str, dict)) and obj.get(key):
            return obj[key]
        for v in obj.values():
            hit = _find_key(v, key, depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj[:12]:
            hit = _find_key(v, key, depth + 1)
            if hit:
                return hit
    return None


def build_runtime_provenance(
    session: Any,
    *,
    version_label: Optional[str] = None,
    group_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Provenance record for one runtime session (never raises)."""
    sig = getattr(session, "signals", {}) or {}
    engine = str(getattr(session, "engine", "") or "")
    project_root = Path(sig["project_root"]) if sig.get("project_root") else None
    src = source_provenance(engine, project_root)

    exe_path = sig.get("paired_executable") or sig.get("executable")
    pck_path = sig.get("pck")
    platform_built = bool(sig.get("built_from_source")) or bool(
        (sig.get("export_attempt") or {}).get("artifact")
    )
    build: Dict[str, Any] = {
        "kind": "none" if not exe_path else ("platform_built" if platform_built else "student_supplied"),
        "executable": file_identity(Path(exe_path)) if exe_path else None,
        "pck": file_identity(Path(pck_path)) if pck_path else None,
    }
    if platform_built:
        # The build is *from* this exact source by construction.
        build["built_from_source_hash"] = src.get("tree_hash")
        build["built_by"] = f"platform:{engine}"
    elif exe_path:
        build["built_by"] = "student"
    # A platform build is deleted after grading: its hash stays as evidence.

    manifest_like = {"signals": sig}
    launcher = _find_key(manifest_like, "launcher")
    finished = time.time()
    status = getattr(getattr(session, "status", None), "value", None)
    return {
        "schema": SCHEMA,
        "version_label": version_label,
        "engine": engine,
        "engine_version": src.get("engine_version"),
        "source_provenance": src,
        "build_provenance": build,
        "runtime_identity": {
            "session_id": getattr(session, "session_id", None),
            "submission_key": getattr(session, "submission_key", None),
            "engine": engine,
            "launcher": launcher if isinstance(launcher, str) else None,
            "started_at": getattr(session, "started_at", None),
            "finished_at": finished,
            "status": status,
        },
        "timestamp": finished,
        "mismatches": detect_mismatches(src, build, group_root=group_root),
        "criteria_evidence": {
            "criteria": list(RUNTIME_CRITERIA),
            "screenshot_count": len(getattr(session, "screenshot_paths", []) or []),
            "manifest": "manifest.json",
        },
    }


def dumps(record: Dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, default=str, sort_keys=True)
