"""GameMaker project detection — .yyp, .yyz, GML trees, builds."""
from __future__ import annotations

import json
import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

GENERATED_RUNTIME_DIRNAME = "_ai_grader_gm_runtime"


def is_generated_gamemaker_runtime_path(path: Path) -> bool:
    return GENERATED_RUNTIME_DIRNAME in Path(path).parts


@dataclass
class GameMakerLayout:
    project_root: Optional[Path] = None
    yyp_path: Optional[Path] = None
    yyz_path: Optional[Path] = None
    gml_files: List[Path] = field(default_factory=list)
    executable: Optional[Path] = None
    html_entry: Optional[Path] = None
    has_objects_tree: bool = False
    resource_count: int = 0
    version_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": str(self.project_root) if self.project_root else None,
            "yyp_path": str(self.yyp_path) if self.yyp_path else None,
            "yyz_path": str(self.yyz_path) if self.yyz_path else None,
            "gml_file_count": len(self.gml_files),
            "executable": str(self.executable) if self.executable else None,
            "html_entry": str(self.html_entry) if self.html_entry else None,
            "has_objects_tree": self.has_objects_tree,
            "resource_count": self.resource_count,
            "version_evidence": self.version_evidence,
        }


def _inside(root: Path, candidate: Path) -> bool:
    """Contain discovery inside one extracted submission, including Arabic paths."""
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _version_rank(path: Path) -> tuple[int, str]:
    """Deterministic policy: an explicit V<n> folder wins, never rglob/mtime order."""
    import re
    versions = [int(m.group(1)) for part in path.parts for m in [re.fullmatch(r"v(\d+)", part, re.I)] if m]
    return (max(versions, default=-1), str(path).casefold())


def resolve_gamemaker_runtime_cwd(executable: Path) -> Path:
    """
    Return the working directory GameMaker exports expect (folder with data.win).

    Students often zip ``V1/`` while the browser shows a nested ``Project/`` folder;
    launching with the wrong cwd can trigger Windows file-picker dialogs.
    """
    exe = executable.resolve()
    if not exe.is_file():
        return exe.parent
    data_win_dir = _find_gamemaker_data_win_directory(exe, max_parent_levels=1)
    if data_win_dir is not None:
        return data_win_dir
    return exe.parent


def _find_gamemaker_data_win_directory(
    executable: Path,
    *,
    search_root: Optional[Path] = None,
    max_parent_levels: int = 0,
) -> Optional[Path]:
    """Locate the folder containing ``data.win`` near a GameMaker export."""
    exe = executable.resolve()
    boundary = search_root.resolve() if search_root is not None else None
    if boundary is not None:
        if boundary.is_file():
            boundary = boundary.parent
        if not _inside(boundary, exe):
            return None
    allowed_root = boundary or (exe.parent.parent if max_parent_levels else exe.parent)
    if allowed_root.is_file():
        allowed_root = allowed_root.parent
    bases = [exe.parent]
    for parent in list(exe.parents)[: max_parent_levels + 1]:
        if boundary is not None and not _inside(boundary, parent):
            break
        try:
            parent.relative_to(allowed_root)
        except ValueError:
            continue
        bases.append(parent)
    for base in bases:
        if (base / "data.win").is_file():
            return base
    roots: List[Path] = []
    if search_root is not None:
        sr = search_root.resolve()
        if sr.is_file():
            sr = sr.parent
        if sr not in roots:
            roots.append(sr)
    for root in roots:
        try:
            for candidate in root.rglob("data.win"):
                if candidate.is_file() and _inside(root, candidate):
                    return candidate.parent
        except OSError:
            continue
    return None


def _gamemaker_version_rank(path: Path) -> int:
    """Return the highest V<number> marker found in a runtime path."""
    versions = []
    for part in path.parent.parts:
        match = re.fullmatch(r"v(\d+)", part.strip(), flags=re.IGNORECASE)
        if match:
            versions.append(int(match.group(1)))
    filename_match = re.search(
        r"(?:^|[^a-z0-9])v(\d+)(?:[^0-9]|$)",
        path.name,
        flags=re.IGNORECASE,
    )
    if filename_match:
        versions.append(int(filename_match.group(1)))
    return max(versions, default=0)


def _artifact_rank(path: Path) -> tuple:
    try:
        stat = path.stat()
        mtime = stat.st_mtime_ns
        size = stat.st_size
    except OSError:
        mtime = size = 0
    return (_gamemaker_version_rank(path), mtime, size, str(path).lower())


def _sample_fingerprint(path: Path) -> str:
    """Stable, bounded fingerprint for comparing large V1/V2 build artifacts."""
    digest = hashlib.sha256()
    try:
        size = path.stat().st_size
        digest.update(str(size).encode("ascii"))
        with path.open("rb") as handle:
            digest.update(handle.read(2 * 1024 * 1024))
            if size > 4 * 1024 * 1024:
                handle.seek(max(0, size - (2 * 1024 * 1024)))
                digest.update(handle.read(2 * 1024 * 1024))
        return digest.hexdigest()
    except OSError:
        return ""


def summarize_gamemaker_versions(root: Path) -> Dict[str, Any]:
    """Describe submitted V1/V2 evidence without treating filenames as achievement."""
    base = root.parent if root.is_file() else root
    by_version: Dict[int, List[Path]] = {}
    try:
        candidates = [
            p for p in base.rglob("*")
            if p.is_file()
            and (p.suffix.lower() in {".yyp", ".yyz", ".exe"} or p.name.lower() == "data.win")
        ]
    except OSError:
        candidates = []
    for candidate in candidates:
        version = _gamemaker_version_rank(candidate)
        if version:
            by_version.setdefault(version, []).append(candidate)

    rows: List[Dict[str, Any]] = []
    for version in sorted(by_version):
        files = sorted(by_version[version], key=_artifact_rank, reverse=True)
        representatives = [
            p for p in files
            if p.name.lower() == "data.win" or p.suffix.lower() in {".yyz", ".yyp"}
        ] or files
        representative = representatives[0] if representatives else None
        rows.append(
            {
                "version": f"V{version}",
                "number": version,
                "file_count": len(files),
                "representative": str(representative) if representative else None,
                "fingerprint": _sample_fingerprint(representative) if representative else "",
                "files": [str(p) for p in files[:12]],
            }
        )

    v1 = next((row for row in rows if row["number"] == 1), None)
    v2 = next((row for row in rows if row["number"] == 2), None)
    comparable = bool(v1 and v2 and v1.get("fingerprint") and v2.get("fingerprint"))
    return {
        "v1_present": bool(v1),
        "v2_present": bool(v2),
        "latest_version": rows[-1]["version"] if rows else None,
        "versions": rows,
        "comparison_available": comparable,
        "updated_version_differs": (
            bool(v1["fingerprint"] != v2["fingerprint"]) if comparable else None
        ),
        "authority": "artifact_version_evidence_only",
    }


def _best_submission_data_win(executable: Path, search_root: Optional[Path]) -> Optional[Path]:
    """Choose the newest submitted GameMaker data bundle for this submission."""
    exe = executable.resolve()
    candidates: List[Path] = []
    sibling = exe.parent / "data.win"
    if sibling.is_file():
        candidates.append(sibling)
    if search_root is not None:
        root = search_root.resolve()
        if root.is_file():
            root = root.parent
        try:
            candidates.extend(p for p in root.rglob("data.win") if p.is_file())
        except OSError:
            pass
    if not candidates:
        return None
    unique = {str(p.resolve()).lower(): p.resolve() for p in candidates}
    return max(
        unique.values(),
        key=lambda p: (
            _gamemaker_version_rank(p),
            p.stat().st_mtime_ns,
            p.stat().st_size,
            str(p).lower(),
        ),
    )


def _stage_gamemaker_runtime_bundle(
    executable: Path,
    data_win: Path,
) -> Dict[str, Any]:
    """Build an isolated runnable bundle without changing the student's upload."""
    exe = executable.resolve()
    data = data_win.resolve()
    stage = Path(tempfile.mkdtemp(prefix="ai_grader_gamemaker_"))
    staged_exe = stage / exe.name
    staged_data = stage / "data.win"
    shutil.copy2(exe, staged_exe)
    shutil.copy2(data, staged_data)
    options_sources = (data.parent / "options.ini", exe.parent / "options.ini")
    for source in options_sources:
        if source.is_file():
            shutil.copy2(source, stage / "options.ini")
            break
    return {
        "runtime_executable": str(staged_exe),
        "runtime_cwd": str(stage),
        "data_win_path": str(staged_data),
        "data_win_source_path": str(data),
        "cleanup_runtime_dir": str(stage),
        "staged": True,
    }


def _submission_anchor_tokens(search_root: Optional[Path]) -> List[str]:
    tokens: List[str] = []
    if search_root is None:
        return tokens
    sr = search_root.resolve()
    for part in [sr, *list(sr.parents)[:5]]:
        name = (part.name or "").strip().lower()
        if not name or name in {"uploads", "students", "project", "v1", "v2", "v3"}:
            continue
        if len(name) >= 3:
            tokens.append(name)
    return tokens


def _archive_member_matches_submission(
    member: str,
    *,
    search_root: Optional[Path],
    version_folder: str,
    wanted_name: str,
) -> bool:
    member_path = PurePosixPath(member)
    if member_path.name.lower() != wanted_name:
        return False
    if member_path.parent.name.lower() != version_folder.lower():
        return False
    anchors = _submission_anchor_tokens(search_root)
    if not anchors:
        return True
    member_lower = member.lower()
    return any(anchor in member_lower for anchor in anchors)


def _candidate_upload_archives(search_root: Optional[Path]) -> List[Path]:
    """Locate teacher upload ZIP/RAR archives that may hold GameMaker runtime assets."""
    archives: List[Path] = []
    seen: set[str] = set()
    roots: List[Path] = []
    if search_root is not None:
        sr = search_root.resolve()
        roots.append(sr if sr.is_dir() else sr.parent)
        # The immediately adjacent upload staging folder is allowed only after
        # the archive/member anchor check below; never recurse through parents.
        parent = sr.parent
        if parent.is_dir():
            roots.extend(sorted(parent.glob("batch_*_upload"), key=lambda p: str(p).casefold()))
    for base in roots:
        if not base.is_dir():
            continue
        patterns = (
            list(base.glob("batch_*_upload/*.zip"))
            + list(base.glob("batch_*_upload/*.rar"))
            + list(base.glob("*.zip"))
            + list(base.glob("*.rar"))
        )
        for archive in patterns:
            key = str(archive.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            archives.append(archive)
    archives.sort(key=lambda p: str(p).casefold())
    return archives


def materialize_gamemaker_runtime_assets(
    executable: Path,
    *,
    search_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Ensure ``data.win`` / ``options.ini`` exist beside a GameMaker export.

    Selective archive extraction can omit large ``data.win`` members; recover them
    from the original upload archive before runtime smoke testing.
    """
    import zipfile

    exe = executable.resolve()
    runtime_dir = exe.parent
    data_win = runtime_dir / "data.win"
    options_ini = runtime_dir / "options.ini"
    result: Dict[str, Any] = {
        "materialized": False,
        "data_win_path": str(data_win) if data_win.is_file() else None,
        "options_ini_path": str(options_ini) if options_ini.is_file() else None,
        "source": "disk" if data_win.is_file() else None,
    }
    if data_win.is_file():
        result["materialized"] = True
        return result

    version_folder = runtime_dir.name
    exe_name = exe.name.lower()
    wanted = {
        "data.win": data_win,
        "options.ini": options_ini,
    }

    anchors = _submission_anchor_tokens(search_root)
    for archive in _candidate_upload_archives(search_root):
        if not archive.is_file():
            continue
        if anchors and not any(anchor in archive.name.lower() for anchor in anchors):
            archive_matches = False
            for anchor in anchors:
                if len(anchor) >= 4 and anchor in str(archive.parent).lower():
                    archive_matches = True
                    break
            if not archive_matches:
                continue
        suffix = archive.suffix.lower()
        try:
            if suffix == ".zip":
                with zipfile.ZipFile(archive, "r") as zf:
                    members = [
                        name
                        for name in zf.namelist()
                        if not name.endswith("/")
                        and (
                            _archive_member_matches_submission(
                                name,
                                search_root=search_root,
                                version_folder=version_folder,
                                wanted_name="data.win",
                            )
                            or _archive_member_matches_submission(
                                name,
                                search_root=search_root,
                                version_folder=version_folder,
                                wanted_name="options.ini",
                            )
                        )
                    ]
                    if not members:
                        continue
                    score = lambda n: (
                        0 if exe_name in n.lower() or exe.stem.lower() in n.lower() else 1,
                        len(n),
                    )
                    for member in sorted(members, key=score):
                        target_name = PurePosixPath(member).name.lower()
                        target_path = wanted.get(target_name)
                        if target_path is None or target_path.is_file():
                            continue
                        target_path.write_bytes(zf.read(member))
                        result["materialized"] = True
                        result["source"] = str(archive)
                        if target_name == "data.win":
                            result["data_win_path"] = str(target_path)
                        if target_name == "options.ini":
                            result["options_ini_path"] = str(target_path)
                    if data_win.is_file():
                        return result
            elif suffix == ".rar":
                from app.archive_extraction_utils import read_rar_member_bytes

                import rarfile  # type: ignore[import-untyped]

                with rarfile.RarFile(str(archive), "r") as rf:
                    members = [
                        info.filename
                        for info in rf.infolist()
                        if not info.isdir()
                        and (
                            _archive_member_matches_submission(
                                info.filename,
                                search_root=search_root,
                                version_folder=version_folder,
                                wanted_name="data.win",
                            )
                            or _archive_member_matches_submission(
                                info.filename,
                                search_root=search_root,
                                version_folder=version_folder,
                                wanted_name="options.ini",
                            )
                        )
                    ]
                    for member in members:
                        target_name = PurePosixPath(member).name.lower()
                        target_path = wanted.get(target_name)
                        if target_path is None or target_path.is_file():
                            continue
                        target_path.write_bytes(read_rar_member_bytes(str(archive), member))
                        result["materialized"] = True
                        result["source"] = str(archive)
                        if target_name == "data.win":
                            result["data_win_path"] = str(target_path)
                    if data_win.is_file():
                        return result
        except Exception:
            continue
    return result


def assess_gamemaker_exe_launch(
    executable: Path,
    *,
    search_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Decide whether a Windows EXE may be launched for GameMaker smoke testing.

    GameMaker runners without ``data.win`` open a modal file-picker — never launch
    in automated batch grading.
    """
    exe = executable.resolve()
    materialize_info = materialize_gamemaker_runtime_assets(exe, search_root=search_root)
    is_gm = _is_gamemaker_exe(exe, project_root=search_root)
    if not is_gm:
        return {
            "is_gamemaker": False,
            "launch_allowed": True,
            "runtime_cwd": str(exe.parent),
            "data_win_path": None,
            "skip_reason": None,
        }

    data_win = _best_submission_data_win(exe, search_root)
    if data_win is None:
        data_win_dir = _find_gamemaker_data_win_directory(exe, search_root=search_root)
        data_win = (data_win_dir / "data.win") if data_win_dir is not None else None
    if data_win is not None and data_win.is_file():
        sibling = exe.parent / "data.win"
        if data_win.resolve() != sibling.resolve():
            staged = _stage_gamemaker_runtime_bundle(exe, data_win)
            return {
                "is_gamemaker": True,
                "launch_allowed": True,
                "skip_reason": None,
                "materialize": materialize_info,
                **staged,
            }
        return {
            "is_gamemaker": True,
            "launch_allowed": True,
            "runtime_executable": str(exe),
            "runtime_cwd": str(data_win.parent),
            "data_win_path": str(data_win),
            "data_win_source_path": str(data_win),
            "staged": False,
            "skip_reason": None,
            "materialize": materialize_info,
        }

    return {
        "is_gamemaker": True,
        "launch_allowed": False,
        "runtime_cwd": str(exe.parent),
        "data_win_path": None,
        "skip_reason": "missing_data_win",
        "materialize": materialize_info,
    }


def _is_gamemaker_exe(path: Path, *, project_root: Optional[Path] = None) -> bool:
    if path.suffix.lower() != ".exe":
        return False
    lower = str(path).lower()
    if "unitycrashhandler" in lower or "unreal" in lower or "console" in path.name.lower():
        return False
    parent = path.parent
    if (parent / "data.win").is_file() or (parent / "options.ini").is_file():
        return True
    # Exports often live in V1/ or bin/ while .yyp sits elsewhere in the tree.
    roots: List[Path] = [parent]
    if project_root and project_root not in roots and _inside(project_root, path):
        roots.append(project_root)
    for base in roots:
        if any(base.rglob("*.yyp")) or any(base.rglob("*.gml")):
            return True
    return False


def _find_html_export(root: Path) -> Optional[Path]:
    for name in ("index.html", "runner.html"):
        direct = root / name
        if direct.is_file():
            return direct
    for candidate in root.rglob("index.html"):
        if "html5" in str(candidate.parent).lower() or "export" in str(candidate.parent).lower():
            return candidate
    for candidate in root.rglob("index.html"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")[:8000].lower()
        except OSError:
            continue
        if "gamemaker" in text or "gms" in text or "html5game" in text:
            return candidate
    return None


def _collect_gml_files(root: Path, limit: int = 200) -> List[Path]:
    found: List[Path] = []
    for fp in root.rglob("*.gml"):
        if len(found) >= limit:
            break
        if any(part.startswith(".") for part in fp.parts):
            continue
        found.append(fp)
    return found


def probe_gamemaker_layout(root: Path) -> GameMakerLayout:
    layout = GameMakerLayout()
    search_root = root.parent if root.is_file() else root
    layout.project_root = search_root

    if root.is_file():
        if root.suffix.lower() == ".yyp":
            layout.yyp_path = root
            layout.project_root = root.parent
        elif root.suffix.lower() == ".yyz":
            layout.yyz_path = root
            layout.project_root = root.parent
        elif root.suffix.lower() == ".exe" and _is_gamemaker_exe(root, project_root=search_root):
            layout.executable = root

    yyp_candidates = list(search_root.rglob("*.yyp"))
    if yyp_candidates:
        layout.yyp_path = max(yyp_candidates, key=_artifact_rank)
        layout.project_root = layout.yyp_path.parent

    if not layout.yyz_path:
        yyz_candidates = list(search_root.rglob("*.yyz"))
        if yyz_candidates:
            layout.yyz_path = max(yyz_candidates, key=_artifact_rank)
            if not layout.yyp_path:
                layout.project_root = layout.yyz_path.parent

    layout.gml_files = _collect_gml_files(layout.project_root or search_root)
    layout.has_objects_tree = any(
        p.name.lower() == "objects" and p.is_dir()
        for p in (layout.project_root or search_root).rglob("*")
        if p.is_dir()
    )

    if not layout.executable:
        # Search only this submission tree. Walking parent folders can mix students.
        search_bases: List[Path] = [search_root]
        if layout.project_root and layout.project_root not in search_bases:
            search_bases.append(layout.project_root)
        candidates: List[Path] = []
        for pr in search_bases[:6]:
            for fp in pr.rglob("*.exe"):
                if is_generated_gamemaker_runtime_path(fp):
                    continue
                if _is_gamemaker_exe(fp, project_root=layout.project_root or pr):
                    candidates.append(fp)
            if candidates:
                break
        if candidates:
            layout.executable = max(candidates, key=_artifact_rank)

    layout.html_entry = _find_html_export(search_root)
    layout.version_evidence = summarize_gamemaker_versions(search_root)
    return layout


def detect_gamemaker_confidence(root: Path) -> float:
    layout = probe_gamemaker_layout(root)
    if layout.yyp_path:
        score = 0.92
        if layout.executable:
            score = 0.96
        elif layout.html_entry:
            score = 0.94
        return score
    if layout.yyz_path:
        return 0.90
    if layout.executable and (layout.gml_files or layout.has_objects_tree):
        return 0.88
    if layout.gml_files and len(layout.gml_files) >= 3:
        return 0.80
    if layout.gml_files:
        return 0.72
    if layout.html_entry:
        return 0.70
    return 0.0


def load_yyp_metadata(yyp_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(yyp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    resources = data.get("resources") or []
    return {
        "ok": True,
        "resource_type": data.get("resourceType"),
        "name": data.get("name") or yyp_path.stem,
        "resource_count": len(resources),
        "meta_version": data.get("MetaData", {}).get("IDEVersion") if isinstance(data.get("MetaData"), dict) else None,
    }
