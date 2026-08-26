"""
PRO GameMaker Runtime Verification — build pipeline, object inspection, gameplay replay.

Pipeline:
  1. Extract .yyz → locate .yyp
  2. Discover the installed GameMaker runtime and build through Igor
  3. Object inspection (sprites/rooms/events/objects)
  4. Gameplay replay (EXE smoke or HTML5 headless) + screenshot comparison
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Optional

from app.runtime_engines.base import RuntimeSession, SessionStatus
from app.runtime_engines.gamemaker.build_runner import analyze_gamemaker_artifacts
from app.runtime_engines.gamemaker.object_inspection import inspect_gamemaker_objects
from app.runtime_engines.gamemaker.project_probe import (
    GENERATED_RUNTIME_DIRNAME,
    GameMakerLayout,
    is_generated_gamemaker_runtime_path,
    probe_gamemaker_layout,
)
from app.runtime_engines.gamemaker.runtime_runner import run_exe_smoke, run_html5_fallback
from app.runtime_engines.gamemaker.toolchain import discover_gamemaker_toolchain
from app.runtime_engines.gamemaker.yyz_parser import extract_yyz_archive, find_yyp_after_extract
from app.runtime_engines.unity.screenshot import compare_runtime_screenshots

logger = logging.getLogger("ai_grader.runtime.gamemaker.verification")


def _version_rank_text(value: str) -> int:
    path = PurePosixPath(value.replace("\\", "/"))
    versions = []
    for part in path.parent.parts:
        match = re.fullmatch(r"v(\d+)", part, re.IGNORECASE)
        if match:
            versions.append(int(match.group(1)))
    filename_match = re.search(
        r"(?:^|[^a-z0-9])v(\d+)(?:[^0-9]|$)", path.name, re.IGNORECASE
    )
    if filename_match:
        versions.append(int(filename_match.group(1)))
    return max(versions, default=0)


def _materialize_yyp_source_tree(yyp_path: Path, workspace: Path) -> Dict[str, Any]:
    """Recover a complete YYP subtree from the staged ZIP before Igor builds it.

    If the staged YYP already has source files beside it, keep that exact project.
    Searching parent upload folders in that case can select a different student's
    archive and silently replace the project that is being graded.
    """
    if yyp_path.is_file():
        try:
            if next(yyp_path.parent.rglob("*.gml"), None) is not None:
                return {
                    "materialized": False,
                    "yyp_path": str(yyp_path),
                    "reason": "source_tree_present",
                }
        except OSError:
            pass

    from app.runtime_engines.gamemaker.project_probe import _candidate_upload_archives

    current_version = _version_rank_text(str(yyp_path))
    anchors = {
        part.lower()
        for part in yyp_path.parts
        if len(part) >= 3 and part.lower() not in {"uploads", "students", "v1", "v2"}
    }
    for archive in _candidate_upload_archives(yyp_path.parent):
        if archive.suffix.lower() != ".zip" or not archive.is_file():
            continue
        try:
            with zipfile.ZipFile(archive, "r") as zf:
                yyp_members = [
                    info for info in zf.infolist()
                    if not info.is_dir() and PurePosixPath(info.filename).suffix.lower() == ".yyp"
                ]
                if not yyp_members:
                    continue
                matching_name = [
                    info for info in yyp_members
                    if PurePosixPath(info.filename).name.lower() == yyp_path.name.lower()
                ]
                candidates = matching_name or yyp_members

                def score(info: zipfile.ZipInfo) -> tuple:
                    low = info.filename.lower()
                    anchor_hits = sum(1 for anchor in anchors if anchor in low)
                    version = _version_rank_text(info.filename)
                    version_match = int(bool(current_version and version == current_version))
                    return version_match, version, anchor_hits, -len(info.filename)

                chosen = max(candidates, key=score)
                prefix = PurePosixPath(chosen.filename).parent
                members = [
                    info for info in zf.infolist()
                    if not info.is_dir()
                    and (
                        prefix == PurePosixPath(".")
                        or PurePosixPath(info.filename).parent == prefix
                        or prefix in PurePosixPath(info.filename).parents
                    )
                ]
                if not members or len(members) > 12000:
                    continue
                total_bytes = sum(max(0, int(info.file_size)) for info in members)
                if total_bytes > 3 * 1024 * 1024 * 1024:
                    continue

                target_root = workspace / "source_archive_project"
                for info in members:
                    member = PurePosixPath(info.filename)
                    relative = member.relative_to(prefix) if prefix != PurePosixPath(".") else member
                    if any(part in {"", ".", ".."} for part in relative.parts):
                        continue
                    target = target_root.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as source, target.open("wb") as dest:
                        shutil.copyfileobj(source, dest, length=1024 * 1024)
                recovered_yyp = target_root / PurePosixPath(chosen.filename).name
                if recovered_yyp.is_file():
                    return {
                        "materialized": True,
                        "archive": str(archive),
                        "member": chosen.filename,
                        "project_root": str(target_root),
                        "yyp_path": str(recovered_yyp),
                        "file_count": len(members),
                        "total_bytes": total_bytes,
                    }
        except (OSError, zipfile.BadZipFile, KeyError, ValueError):
            continue
    return {"materialized": False, "yyp_path": str(yyp_path)}


def publish_built_runtime_to_student(package_dir: Path, student_root: Path) -> Dict[str, Any]:
    """Copy a built GameMaker package into the student folder for launch."""
    dest = student_root.resolve() / GENERATED_RUNTIME_DIRNAME
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in package_dir.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(package_dir)
        if any(part in {"", ".", ".."} for part in relative.parts):
            continue
        target = dest.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    exe = next(dest.rglob("*.exe"), None)
    html = next(dest.rglob("index.html"), None)
    return {
        "generated": True,
        "generated_runtime_dir": str(dest),
        "package_dir": str(package_dir),
        "executable": str(exe.resolve()) if exe else None,
        "html_entry": str(html.resolve()) if html else None,
        "copied_files": copied,
    }


def cleanup_generated_gamemaker_runtime(
    generated_dir: Optional[Path],
    *,
    student_root: Path,
) -> Dict[str, Any]:
    """Delete only the grader-built runtime folder inside the student tree."""
    if not generated_dir:
        return {"cleaned": False, "reason": "none"}
    dest = Path(generated_dir).resolve()
    root = student_root.resolve()
    if dest.name != GENERATED_RUNTIME_DIRNAME or not is_generated_gamemaker_runtime_path(dest):
        return {"cleaned": False, "reason": "unsafe_name", "path": str(dest)}
    try:
        dest.relative_to(root)
    except ValueError:
        return {"cleaned": False, "reason": "outside_student_root", "path": str(dest)}
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    return {"cleaned": not dest.exists(), "path": str(dest)}


def run_build_pipeline(
    layout: GameMakerLayout,
    *,
    workspace: Path,
    timeout_seconds: int = 90,
    student_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Extract YYZ/YYP and optionally invoke GameMaker IDE CLI build."""
    pipeline: Dict[str, Any] = {
        "version": "gamemaker_build_pipeline_v1",
        "yyz_extracted": False,
        "yyp_ready": bool(layout.yyp_path),
        "ide_build_attempted": False,
        "runnable_after_pipeline": bool(layout.executable or layout.html_entry),
        "student_runtime": {"generated": False},
    }
    publish_root = student_root or layout.project_root

    if layout.yyz_path and not layout.yyp_path:
        extract_dir = workspace / "yyz_extract"
        extract_result = extract_yyz_archive(layout.yyz_path, extract_dir)
        pipeline["yyz_extract"] = extract_result
        if extract_result.get("success"):
            pipeline["yyz_extracted"] = True
            yyp = find_yyp_after_extract(extract_result)
            if yyp:
                layout.yyp_path = yyp
                layout.project_root = yyp.parent
                layout.gml_files = list(yyp.parent.rglob("*.gml"))[:200]
                pipeline["yyp_ready"] = True

    if layout.yyp_path and not (layout.executable or layout.html_entry):
        source_tree = _materialize_yyp_source_tree(layout.yyp_path, workspace)
        pipeline["source_tree_materialization"] = source_tree
        if source_tree.get("materialized") and source_tree.get("yyp_path"):
            layout.yyp_path = Path(str(source_tree["yyp_path"]))
            layout.project_root = layout.yyp_path.parent
            layout.gml_files = list(layout.project_root.rglob("*.gml"))[:200]
        ide_build = _try_ide_build(layout.yyp_path, workspace, timeout_seconds=timeout_seconds)
        pipeline["ide_build"] = ide_build
        pipeline["ide_build_attempted"] = bool(ide_build.get("attempted"))
        package_exe = Path(str(ide_build["executable"])) if ide_build.get("executable") else None
        if package_exe and publish_root:
            published = publish_built_runtime_to_student(package_exe.parent, Path(publish_root))
            pipeline["student_runtime"] = published
            if published.get("executable"):
                layout.executable = Path(str(published["executable"]))
                ide_build["executable"] = published["executable"]
            if published.get("html_entry"):
                layout.html_entry = Path(str(published["html_entry"]))
                ide_build["html_entry"] = published["html_entry"]
        elif package_exe:
            layout.executable = package_exe
        if ide_build.get("html_entry") and not layout.html_entry:
            layout.html_entry = Path(str(ide_build["html_entry"]))

    refreshed = probe_gamemaker_layout(layout.yyp_path or layout.yyz_path or layout.project_root or workspace)
    if refreshed.executable:
        layout.executable = refreshed.executable
    if refreshed.html_entry:
        layout.html_entry = refreshed.html_entry
    if refreshed.gml_files:
        layout.gml_files = refreshed.gml_files

    published_runtime = pipeline.get("student_runtime") or {}
    if published_runtime.get("executable"):
        layout.executable = Path(str(published_runtime["executable"]))
    if published_runtime.get("html_entry"):
        layout.html_entry = Path(str(published_runtime["html_entry"]))

    pipeline["runnable_after_pipeline"] = bool(layout.executable or layout.html_entry)
    pipeline["layout"] = layout.to_dict()
    return pipeline


def _try_ide_build(yyp_path: Path, workspace: Path, *, timeout_seconds: int) -> Dict[str, Any]:
    """Build a Windows package with GameMaker's supported Igor command line."""
    toolchain = discover_gamemaker_toolchain()
    if not toolchain.ready:
        return {
            "attempted": False,
            "reason": toolchain.reason,
            "toolchain": toolchain.to_dict(),
        }
    out_dir = workspace / "ide_build"
    cache_dir = workspace / "igor_cache"
    temp_dir = workspace / "igor_temp"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    target_zip = out_dir / "gamemaker_windows_build.zip"
    cmd = [
        str(toolchain.igor_path),
        f"/uf={toolchain.user_folder}",
        f"/rp={toolchain.runtime_root}",
        f"/project={yyp_path.resolve()}",
        f"/cache={cache_dir.resolve()}",
        f"/temp={temp_dir.resolve()}",
        f"/of={out_dir.resolve()}",
        f"/tf={target_zip.name}",
        "--",
        "Windows",
        "PackageZip",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=min(max(timeout_seconds, 30), 300),
            cwd=str(yyp_path.parent),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "attempted": True,
            "success": False,
            "reason": "igor_build_failed",
            "detail": str(exc),
            "toolchain": toolchain.to_dict(),
        }

    archives = sorted(out_dir.rglob("*.zip"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    if proc.returncode == 0 and archives:
        extract_dir = out_dir / "windows_package"
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.unpack_archive(str(archives[0]), str(extract_dir))
        except (OSError, shutil.ReadError) as exc:
            return {
                "attempted": True,
                "success": False,
                "reason": "igor_package_extract_failed",
                "detail": str(exc),
                "returncode": proc.returncode,
                "toolchain": toolchain.to_dict(),
            }
        exe = next(extract_dir.rglob("*.exe"), None)
        html = next(extract_dir.rglob("index.html"), None)
        if exe or html:
            return {
                "attempted": True,
                "success": True,
                "command": cmd,
                "returncode": proc.returncode,
                "package": str(archives[0]),
                "executable": str(exe) if exe else None,
                "html_entry": str(html) if html else None,
                "toolchain": toolchain.to_dict(),
            }

    detail = (proc.stderr or proc.stdout or "")[-2000:]
    return {
        "attempted": True,
        "success": False,
        "reason": "igor_build_failed" if proc.returncode else "igor_build_missing_output",
        "returncode": proc.returncode,
        "detail": detail,
        "toolchain": toolchain.to_dict(),
    }


def run_gameplay_replay(
    session: RuntimeSession,
    layout: GameMakerLayout,
    *,
    timeout_seconds: int = 45,
) -> Dict[str, Any]:
    """Launch runnable build, capture screenshots, compare frame deltas."""
    replay: Dict[str, Any] = {
        "version": "gamemaker_gameplay_replay_v1",
        "method": "none",
        "screenshots": [],
        "comparison": {},
    }

    if layout.executable:
        smoke = run_exe_smoke(session, layout.executable, timeout_seconds=timeout_seconds)
        runtime_method = str(session.signals.get("runtime_method") or "")
        if runtime_method in {
            "gamemaker_static_only",
            "gamemaker_runtime_unavailable",
        } or smoke.get("skipped"):
            replay["method"] = "static_only"
            replay["skipped"] = True
            replay["reason"] = (
                smoke.get("reason")
                or (session.signals.get("gamemaker_launch_assessment") or {}).get("skip_reason")
                or "missing_data_win"
            )
        else:
            replay["method"] = "exe_smoke"
    elif layout.html_entry:
        run_html5_fallback(session, layout.html_entry, timeout_seconds=timeout_seconds)
        replay["method"] = "html5_headless"
    else:
        replay["skipped"] = True
        replay["reason"] = "no_runnable_build"
        return replay

    shots = [str(p) for p in session.screenshot_paths]
    replay["screenshots"] = shots
    replay["comparison"] = compare_runtime_screenshots(shots)
    replay["gameplay_observed"] = bool(shots) and replay["comparison"].get("comparison_available", False)
    replay["freeze_detected"] = bool(replay["comparison"].get("freeze_detected"))
    replay["frame_delta_score"] = float(replay["comparison"].get("frame_delta_score") or 0.0)
    return replay


def run_gamemaker_runtime_verification(
    session: RuntimeSession,
    layout: GameMakerLayout,
    *,
    timeout_seconds: int = 90,
) -> Dict[str, Any]:
    """Full PRO verification pipeline."""
    workspace = session.workspace
    generated_dir: Optional[Path] = None
    build: Dict[str, Any] = {}
    result: Optional[Dict[str, Any]] = None
    try:
        stale = session.root / GENERATED_RUNTIME_DIRNAME
        if stale.is_dir():
            cleanup_generated_gamemaker_runtime(stale, student_root=session.root)

        build = run_build_pipeline(
            layout,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            student_root=session.root,
        )
        generated = (build.get("student_runtime") or {}).get("generated_runtime_dir")
        if generated:
            generated_dir = Path(str(generated))
            session.signals["generated_runtime_dir"] = str(generated_dir)
        inspection = inspect_gamemaker_objects(layout)
        replay = run_gameplay_replay(session, layout, timeout_seconds=min(90, timeout_seconds))

        artifact = analyze_gamemaker_artifacts(layout)
        signals = {
            "gamemaker_build_pipeline_ok": build.get("runnable_after_pipeline"),
            "object_inspection_ok": inspection.get("inspection_ok"),
            "object_count": (inspection.get("summary") or {}).get("objects", 0),
            "sprite_count": (inspection.get("summary") or {}).get("sprites", 0),
            "room_count": (inspection.get("summary") or {}).get("rooms", 0),
            "event_count": (inspection.get("summary") or {}).get("events", 0),
            "gameplay_replay_ok": replay.get("gameplay_observed"),
            "screenshot_count": len(replay.get("screenshots") or []),
            "frame_delta_score": replay.get("frame_delta_score", 0.0),
            "freeze_detected": replay.get("freeze_detected", False),
            "functional_smoke_pass": bool(
                build.get("runnable_after_pipeline")
                and inspection.get("inspection_ok")
                and replay.get("gameplay_observed")
                and replay.get("method") in ("exe_smoke", "html5_headless")
            ),
        }

        result = {
            "success": signals["functional_smoke_pass"] or signals["object_inspection_ok"],
            "method": "gamemaker_pro_runtime_verification",
            "build_pipeline": build,
            "object_inspection": inspection,
            "gameplay_replay": replay,
            "artifact_analysis": artifact,
            "signals": signals,
            "gamemaker_runtime_verification": {
                "version": "gamemaker_runtime_verification_v1",
                "yyp": str(layout.yyp_path) if layout.yyp_path else None,
                "yyz": str(layout.yyz_path) if layout.yyz_path else None,
                "version_evidence": layout.version_evidence,
            },
        }

        session.signals.update(signals)
        session.signals["build_pipeline"] = build
        session.signals["object_inspection"] = inspection
        session.signals["gameplay_replay"] = replay
        session.signals["artifact_analysis"] = artifact
        session.signals["gamemaker_runtime_verification"] = result["gamemaker_runtime_verification"]
        session.signals["gamemaker_version_evidence"] = layout.version_evidence
        session.signals["runtime_method"] = result["method"]

        if replay.get("gameplay_observed"):
            session.status = SessionStatus.COMPLETED
        elif inspection.get("inspection_ok") and build.get("yyp_ready"):
            session.status = SessionStatus.COMPLETED
            session.signals["runtime_partial"] = True
        else:
            session.status = SessionStatus.FAILED if not build.get("yyp_ready") else SessionStatus.COMPLETED

        session.events.record(
            "gamemaker_pro_runtime_verification",
            objects=signals["object_count"],
            rooms=signals["room_count"],
            gameplay=signals["gameplay_replay_ok"],
        )
        return result
    finally:
        cleanup = cleanup_generated_gamemaker_runtime(generated_dir, student_root=session.root)
        session.signals["generated_runtime_cleanup"] = cleanup
        if result is not None:
            result["signals"]["generated_runtime_cleanup"] = cleanup

