"""Frame extraction from runtime artifacts — temporal sequence, not single images."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _timestamp_from_name(path: Path, index: int, interval: float = 1.0) -> float:
    match = re.search(r"frame[_-]?(\d+)", path.stem, re.I)
    if match:
        return float(match.group(1)) * interval
    match = re.search(r"_(\d{2,4})\.", path.name)
    if match:
        return float(match.group(1)) * interval
    return float(index) * interval


def extract_frames_from_directory(
    directory: Path,
    *,
    interval_seconds: float = 1.0,
    max_frames: int = 48,
) -> Tuple[List[Path], List[float]]:
    if not directory.is_dir():
        return [], []

    candidates = sorted(
        [
            p
            for p in directory.rglob("*")
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ],
        key=lambda p: p.name.lower(),
    )
    frames = candidates[:max_frames]
    timestamps = [_timestamp_from_name(p, i, interval_seconds) for i, p in enumerate(frames)]
    return frames, timestamps


def extract_frames_from_video(
    video_path: Path,
    output_dir: Path,
    *,
    interval_seconds: float = 1.0,
    max_frames: int = 24,
) -> Tuple[List[Path], List[float], Dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    meta: Dict[str, Any] = {"video_path": str(video_path), "method": "none"}

    try:
        from app.project_intelligence.video_runtime_extractor import _extract_frames_ffmpeg

        frames_meta, err = _extract_frames_ffmpeg(video_path, output_dir, interval_seconds, max_frames)
        if frames_meta:
            paths = [Path(item["path"]) for item in frames_meta if item.get("path")]
            timestamps = [float(item.get("timestamp_seconds") or 0.0) for item in frames_meta]
            meta.update({"method": "ffmpeg", "frame_count": len(paths)})
            return paths[:max_frames], timestamps[:max_frames], meta
        meta["ffmpeg_error"] = err
    except Exception as exc:
        meta["ffmpeg_exception"] = str(exc)

    # OpenCV fallback
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            meta["error"] = "video_open_failed"
            return [], [], meta
        fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
        step = max(int(fps * interval_seconds), 1)
        paths: List[Path] = []
        timestamps: List[float] = []
        index = 0
        frame_idx = 0
        while cap.isOpened() and len(paths) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step == 0:
                out = output_dir / f"video_frame_{index:04d}.png"
                cv2.imwrite(str(out), frame)
                paths.append(out)
                timestamps.append(frame_idx / fps)
                index += 1
            frame_idx += 1
        cap.release()
        meta.update({"method": "opencv", "frame_count": len(paths)})
        return paths, timestamps, meta
    except Exception as exc:
        meta["opencv_exception"] = str(exc)
        return [], [], meta


def build_frame_sequence(
    artifact_root: Path,
    *,
    video_path: Optional[Path] = None,
    interval_seconds: float = 1.0,
) -> Tuple[List[Path], List[float], Dict[str, Any]]:
    screenshots_dir = artifact_root / "screenshots"
    frames, timestamps = extract_frames_from_directory(
        screenshots_dir, interval_seconds=interval_seconds
    )
    meta: Dict[str, Any] = {"source": "screenshots", "frame_count": len(frames)}

    if video_path and video_path.is_file():
        video_frames_dir = artifact_root / "gameplay_video" / "extracted_frames"
        v_paths, v_ts, v_meta = extract_frames_from_video(
            video_path, video_frames_dir, interval_seconds=interval_seconds
        )
        if v_paths:
            # Prefer video temporal sequence when available
            frames = v_paths
            timestamps = v_ts
            meta = {"source": "video", **v_meta}

    return frames, timestamps, meta
