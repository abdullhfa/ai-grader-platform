"""
BASIC-only: temp video → 5 percentile keyframes (FFmpeg) → Vision budget (no .mp4 on disk).
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.project_intelligence.video_runtime_extractor import (
    BASIC_KEYFRAME_PERCENTILES,
    VIDEO_EXTENSIONS,
    extract_percentile_keyframes,
    list_submission_video_files,
)

_SKIP_VIDEO_DIRS = frozenset(
    {".godot", ".import", "node_modules", "library", "temp", "bin", "obj", "embedruntime"}
)


def _norm_rel(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _video_rels_from_intake(intake_relative_paths: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in intake_relative_paths or []:
        rel = _norm_rel(raw)
        if not rel:
            continue
        if Path(rel).suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        key = rel.lower()
        if key not in seen:
            seen.add(key)
            out.append(rel)
    return out


def _resolve_video_on_disk(rel: str, workspace_root: Path) -> Optional[Path]:
    rel_path = Path(rel)
    candidates = [workspace_root / rel_path, workspace_root / rel_path.name]
    for c in candidates:
        try:
            if (
                c.is_file()
                and c.suffix.lower() in VIDEO_EXTENSIONS
                and _path_under_workspace(c, workspace_root)
            ):
                return c.resolve()
        except OSError:
            continue
    return None


def _find_zip_member(zf: zipfile.ZipFile, rel_path: str) -> Optional[str]:
    target = _norm_rel(rel_path).lower()
    names = [_norm_rel(n) for n in zf.namelist() if not n.endswith("/")]
    for n in names:
        if n.lower() == target:
            return n
    base = Path(rel_path).name.lower()
    for n in names:
        if Path(n).name.lower() == base:
            return n
    for n in names:
        if n.lower().endswith("/" + base) or n.lower().endswith(target):
            return n
    return None


def _materialize_video_temp(
    rel_path: str,
    *,
    source_archive: Optional[str],
) -> Tuple[Optional[Path], Optional[Path]]:
    """Write one video member to a temp dir; return (video_path, cleanup_dir)."""
    if not source_archive:
        return None, None
    archive = Path(source_archive)
    if not archive.is_file():
        return None, None

    cleanup = Path(tempfile.mkdtemp(prefix="basic_vid_src_"))
    out_video = cleanup / Path(rel_path).name

    ext = archive.suffix.lower()
    try:
        if ext == ".zip":
            with zipfile.ZipFile(archive, "r") as zf:
                member = _find_zip_member(zf, rel_path)
                if not member:
                    shutil.rmtree(cleanup, ignore_errors=True)
                    return None, None
                out_video.write_bytes(zf.read(member))
        elif ext == ".rar":
            from app.archive_extraction_utils import read_rar_member_bytes

            member = _norm_rel(rel_path)
            try:
                import rarfile  # type: ignore

                from app.archive_extraction_utils import _apply_rarfile_unrar_tool

                _apply_rarfile_unrar_tool()
                with rarfile.RarFile(str(archive), "r") as rf:
                    names = [_norm_rel(n) for n in rf.namelist() if not n.endswith("/")]
                    pick = member if member in names else None
                    if not pick:
                        base = Path(rel_path).name.lower()
                        pick = next(
                            (n for n in names if Path(n).name.lower() == base),
                            None,
                        )
                    if not pick:
                        shutil.rmtree(cleanup, ignore_errors=True)
                        return None, None
                    member = pick
            except Exception:
                member = Path(rel_path).name
            out_video.write_bytes(read_rar_member_bytes(str(archive), member))
        else:
            shutil.rmtree(cleanup, ignore_errors=True)
            return None, None
    except Exception:
        shutil.rmtree(cleanup, ignore_errors=True)
        return None, None

    if not out_video.is_file() or out_video.stat().st_size < 1024:
        shutil.rmtree(cleanup, ignore_errors=True)
        return None, None
    return out_video, cleanup


def _mime_for_frame(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")


def format_basic_video_keyframes_status_ar(meta: Optional[Dict[str, Any]]) -> str:
    """Human-readable BASIC video keyframe summary for UI/PDF."""
    m = meta or {}
    videos = int(m.get("videos_found") or 0)
    frames = int(m.get("frames_extracted") or 0)
    per = int(m.get("frames_per_video") or 5)
    if videos <= 0:
        return ""
    if frames <= 0:
        errs = m.get("errors") or []
        hint = str(errs[0])[:80] if errs else "FFmpeg"
        return f"فيديو ×{videos} — لم تُستخرج إطارات ({hint})"
    return f"{per} إطار/فيديو × {videos} فيديو → {frames} صورة (تحليل بصري)"


def _path_under_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except (OSError, ValueError):
        return False


_DOC_PRIMARY_EXT = frozenset({".doc", ".docx", ".pdf", ".pptx", ".rtf"})


def _resolve_submission_workspace(
    primary: str,
    submission_paths: List[str],
    *,
    student_name: str = "",
) -> Path:
    from app.evidence_completeness_gate import resolve_student_submission_root

    pp = Path(primary) if primary else None
    if pp and pp.is_file() and pp.suffix.lower() in _DOC_PRIMARY_EXT:
        return pp.parent.resolve()
    root = resolve_student_submission_root(
        primary or (submission_paths[0] if submission_paths else ""),
        student_name=student_name,
    )
    return root.resolve()


def _rel_belongs_to_student_intake(rel: str, workspace: Path) -> bool:
    """Archive/disk rel paths must live under the student workspace folder name."""
    rel_l = _norm_rel(rel).lower()
    ws = workspace.name.lower()
    parts = rel_l.split("/")
    if len(parts) > 1:
        return parts[0] == ws
    return True


def _discover_videos_on_disk(workspace_root: Path) -> List[Path]:
    """Walk **only** the student workspace — never sibling batch folders."""
    direct: List[Path] = []
    seen: set[str] = set()
    if not workspace_root.is_dir():
        return []
    try:
        for fp in workspace_root.rglob("*"):
            if not fp.is_file() or fp.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            try:
                rel_parts = fp.relative_to(workspace_root).parts
            except ValueError:
                continue
            if any(part.lower() in _SKIP_VIDEO_DIRS for part in rel_parts[:-1]):
                continue
            key = str(fp.resolve()).lower()
            if key not in seen:
                seen.add(key)
                direct.append(fp.resolve())
    except OSError:
        return []
    return sorted(direct, key=lambda x: str(x).lower())


def _list_videos_in_archive(source_archive: str) -> List[str]:
    """List video member paths inside ZIP/RAR without writing .mp4 to disk (BASIC)."""
    archive = Path(source_archive)
    if not archive.is_file():
        return []
    out: List[str] = []
    seen: set[str] = set()
    ext = archive.suffix.lower()
    try:
        if ext == ".zip":
            with zipfile.ZipFile(archive, "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    rel = _norm_rel(name)
                    if Path(rel).suffix.lower() not in VIDEO_EXTENSIONS:
                        continue
                    key = rel.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(rel)
        elif ext == ".rar":
            import rarfile  # type: ignore

            from app.archive_extraction_utils import _apply_rarfile_unrar_tool

            _apply_rarfile_unrar_tool()
            with rarfile.RarFile(str(archive), "r") as rf:
                for name in rf.namelist():
                    if not name or name.endswith("/"):
                        continue
                    rel = _norm_rel(name)
                    if Path(rel).suffix.lower() not in VIDEO_EXTENSIONS:
                        continue
                    key = rel.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(rel)
    except Exception:
        return []
    return sorted(out, key=lambda x: x.lower())


def _load_vision_bytes(frame_paths: List[Path]) -> List[Tuple[bytes, str]]:
    """Return (bytes, mime_type) tuples — mime must be valid for Vision APIs."""
    images: List[Tuple[bytes, str]] = []
    for fp in frame_paths:
        try:
            if fp.is_file() and fp.stat().st_size >= 512:
                images.append((fp.read_bytes(), _mime_for_frame(fp)))
        except OSError:
            continue
    return images


def extract_basic_video_keyframe_images(
    student_info: Dict[str, Any],
    *,
    max_frames_per_video: Optional[int] = None,
    max_videos: Optional[int] = None,
) -> Tuple[List[Tuple[bytes, str]], Dict[str, Any]]:
    """
    BASIC: up to ``max_frames_per_video`` PNG keyframes **per video**
    (default 5 × up to 2 videos). Temp videos are deleted after extraction.
    """
    from app.grading_mode_policy import basic_max_video_keyframes, basic_max_videos

    per_video = (
        max_frames_per_video
        if max_frames_per_video is not None
        else basic_max_video_keyframes()
    )
    video_limit = max_videos if max_videos is not None else basic_max_videos()
    meta: Dict[str, Any] = {
        "version": 2,
        "videos_found": 0,
        "frames_extracted": 0,
        "frames_per_video": per_video,
        "max_videos": video_limit,
        "sources": [],
        "errors": [],
        "method": "basic_percentile_keyframes_per_video",
    }
    if per_video <= 0:
        return [], meta

    primary = str(student_info.get("path") or "")
    submission_paths = [str(p) for p in (student_info.get("submission_paths") or [])]
    intake_rels = _video_rels_from_intake(list(student_info.get("intake_relative_paths") or []))
    source_archive = student_info.get("source_archive_path")
    workspace = _resolve_submission_workspace(
        primary,
        submission_paths,
        student_name=str(student_info.get("name") or ""),
    )
    meta["submission_workspace"] = str(workspace)
    rejected_cross_student: List[str] = []

    video_sources: List[Tuple[str, Optional[Path]]] = []
    seen_names: set[str] = set()

    def _register(label: str, disk: Optional[Path]) -> None:
        if disk is not None and not _path_under_workspace(disk, workspace):
            rejected_cross_student.append(label)
            return
        base = Path(label).name.lower()
        if base in seen_names:
            return
        seen_names.add(base)
        video_sources.append((label, disk))

    for vp in _discover_videos_on_disk(workspace):
        _register(str(vp.relative_to(workspace)).replace("\\", "/"), vp)

    for vp in list_submission_video_files([Path(p) for p in submission_paths]):
        if _path_under_workspace(vp, workspace):
            _register(vp.name, vp)
        else:
            rejected_cross_student.append(str(vp))

    archive_videos: List[str] = []
    if source_archive:
        archive_videos = _list_videos_in_archive(str(source_archive))

    for rel in list(dict.fromkeys([*intake_rels, *archive_videos])):
        if not _rel_belongs_to_student_intake(rel, workspace):
            rejected_cross_student.append(rel)
            continue
        base = Path(rel).name.lower()
        if base in seen_names:
            continue
        on_disk = _resolve_video_on_disk(rel, workspace)
        if on_disk is not None:
            _register(rel, on_disk)
        elif source_archive:
            _register(rel, None)

    if rejected_cross_student:
        meta["rejected_cross_student_videos"] = rejected_cross_student[:20]
        meta["errors"].append(
            f"isolation_rejected:{len(rejected_cross_student)}"
        )

    meta["videos_found"] = len(video_sources)
    if not video_sources:
        return [], meta

    frames_root = Path(tempfile.mkdtemp(prefix="basic_vid_kf_"))
    frame_paths: List[Path] = []
    temp_cleanups: List[Path] = []
    pct_full = BASIC_KEYFRAME_PERCENTILES
    use_pcts = pct_full[:per_video] if len(pct_full) >= per_video else pct_full

    try:
        for rel_label, disk_path in video_sources[:video_limit]:
            cleanup_src: Optional[Path] = None
            video_path = disk_path
            if video_path is None:
                video_path, cleanup_src = _materialize_video_temp(
                    rel_label, source_archive=str(source_archive or "")
                )
                if cleanup_src:
                    temp_cleanups.append(cleanup_src)
            if video_path is None or not video_path.is_file():
                meta["errors"].append(f"missing_video:{rel_label}")
                continue

            out_dir = frames_root / Path(rel_label).stem
            items, err = extract_percentile_keyframes(
                video_path,
                out_dir,
                percentiles=use_pcts,
            )
            if err:
                meta["errors"].append(f"{Path(rel_label).name}:{err}"[:200])
            video_frames: List[Path] = []
            for item in items:
                fp = Path(str(item.get("frame_path") or ""))
                if fp.is_file():
                    video_frames.append(fp)
            frame_paths.extend(video_frames[:per_video])
            meta["sources"].append(
                {
                    "label": rel_label,
                    "frames": len(video_frames[:per_video]),
                    "frames_requested": per_video,
                    "from_archive_temp": disk_path is None,
                }
            )

        meta["frames_extracted"] = len(frame_paths)
        return _load_vision_bytes(frame_paths), meta
    finally:
        for d in temp_cleanups:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(frames_root, ignore_errors=True)


def merge_basic_vision_images(
    word_images: List[Tuple[bytes, str]],
    video_images: List[Tuple[bytes, str]],
    *,
    max_word: int,
    max_video: int,
) -> Tuple[List[Tuple[bytes, str]], Dict[str, int]]:
    """BASIC: up to ``max_word`` from Word (0 = all) + up to ``max_video`` from video keyframes."""
    word_take = len(word_images) if max_word <= 0 else min(len(word_images), max_word)
    video_take = min(len(video_images), max_video)
    merged = list(word_images[:word_take]) + list(video_images[:video_take])
    stats = {
        "word_images": word_take,
        "video_keyframes": video_take,
        "total_vision": word_take + video_take,
    }
    return merged, stats
