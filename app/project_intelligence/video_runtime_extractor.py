"""
Deterministic video frame sampling for runtime evidence (no vision / OCR / ASR).

Uses ffmpeg when available, else OpenCV. One frame every ~interval_seconds, capped.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}
)
DEFAULT_INTERVAL_SECONDS = 3.0
BASIC_KEYFRAME_PERCENTILES = (0.0, 0.25, 0.5, 0.75, 1.0)
MAX_INPUT_VIDEOS = 2
MAX_FRAMES_PER_VIDEO = 12
MAX_FRAMES_TOTAL = 24
MAX_DURATION_SECONDS = 300.0


def _ffprobe_duration_seconds(video_path: Path) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        return float((proc.stdout or "").strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _extract_frames_ffmpeg(
    video_path: Path,
    frames_dir: Path,
    interval_seconds: float,
    max_frames: int,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return [], "ffmpeg_not_found"
    out_pattern = frames_dir / f"{video_path.stem}_%04d.png"
    vf = f"fps=1/{interval_seconds}"
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                vf,
                "-frames:v",
                str(max_frames),
                str(out_pattern),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            return [], (proc.stderr or proc.stdout or "ffmpeg_failed")[:500]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)[:300]

    paths = sorted(frames_dir.glob(f"{video_path.stem}_*.png"))
    items: List[Dict[str, Any]] = []
    for i, fp in enumerate(paths):
        ts = round(i * interval_seconds, 3)
        items.append(
            {
                "evidence_type": "video_frame",
                "timestamp_seconds": ts,
                "source": video_path.name,
                "frame_path": str(fp.resolve()),
            }
        )
    return items, None


def _timestamp_for_percentile(duration: float, percentile: float) -> float:
    if duration <= 0:
        return 0.0
    if percentile >= 1.0:
        return max(0.0, duration - 0.15)
    return max(0.0, min(duration * percentile, max(0.0, duration - 0.05)))


def _extract_single_frame_ffmpeg(
    ffmpeg: str,
    video_path: Path,
    out_path: Path,
    timestamp_seconds: float,
) -> Optional[str]:
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp_seconds:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            return (proc.stderr or proc.stdout or "ffmpeg_frame_failed")[:400]
        if not out_path.is_file() or out_path.stat().st_size < 512:
            return "ffmpeg_empty_frame"
        return None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)[:300]


def extract_percentile_keyframes(
    video_path: Path,
    frames_dir: Path,
    *,
    percentiles: Tuple[float, ...] = BASIC_KEYFRAME_PERCENTILES,
    max_duration_seconds: float = MAX_DURATION_SECONDS,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Extract evenly spaced keyframes at 0/25/50/75/100% of duration (BASIC vision).
    Uses ffmpeg -ss seek; falls back to OpenCV if ffmpeg unavailable.
    """
    frames_dir.mkdir(parents=True, exist_ok=True)
    if not video_path.is_file():
        return [], "video_not_found"

    dur = _ffprobe_duration_seconds(video_path)
    if dur is not None and dur > max_duration_seconds:
        return [], f"video_too_long:{video_path.name}"

    ffmpeg = shutil.which("ffmpeg")
    items: List[Dict[str, Any]] = []
    errors: List[str] = []

    if ffmpeg:
        effective_dur = dur if dur is not None and dur > 0 else None
        for i, pct in enumerate(percentiles):
            ts = _timestamp_for_percentile(effective_dur or 0.0, pct) if effective_dur else float(i)
            out_path = frames_dir / f"{video_path.stem}_pct{int(pct * 100):03d}.png"
            err = _extract_single_frame_ffmpeg(ffmpeg, video_path, out_path, ts)
            if err:
                errors.append(err)
                continue
            items.append(
                {
                    "evidence_type": "video_keyframe",
                    "timestamp_seconds": round(ts, 3),
                    "percentile": pct,
                    "source": video_path.name,
                    "frame_path": str(out_path.resolve()),
                }
            )
        if items:
            return items, None

    # OpenCV fallback — sample by frame index at percentiles
    try:
        import cv2  # type: ignore
    except ImportError:
        return [], errors[0] if errors else "ffmpeg_not_found"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], "opencv_open_failed"
    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = (cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if frame_count <= 0:
            frame_count = max(1, int((dur or 1.0) * fps))
        for i, pct in enumerate(percentiles):
            idx = 0 if frame_count <= 1 else min(frame_count - 1, (round((frame_count - 1) * pct)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            out_path = frames_dir / f"{video_path.stem}_pct{int(pct * 100):03d}.png"
            if not cv2.imwrite(str(out_path), frame):
                continue
            ts = idx / fps if fps > 0 else float(i)
            items.append(
                {
                    "evidence_type": "video_keyframe",
                    "timestamp_seconds": round(ts, 3),
                    "percentile": pct,
                    "source": video_path.name,
                    "frame_path": str(out_path.resolve()),
                }
            )
        return items, None if items else (errors[0] if errors else "opencv_no_frames")
    finally:
        cap.release()


def _extract_frames_opencv(
    video_path: Path,
    frames_dir: Path,
    interval_seconds: float,
    max_frames: int,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        import cv2  # type: ignore
    except ImportError:
        return [], "opencv_not_found"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], "opencv_open_failed"
    try:
        fps = (cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if fps <= 1e-6:
            fps = 25.0
        step = max(1, (round(fps * interval_seconds)))
        items: List[Dict[str, Any]] = []
        idx = 0
        out_i = 0
        while out_i < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                ts = round(out_i * interval_seconds, 3)
                out_path = frames_dir / f"{video_path.stem}_{out_i:04d}.png"
                if not cv2.imwrite(str(out_path), frame):
                    return items, "opencv_imwrite_failed"
                items.append(
                    {
                        "evidence_type": "video_frame",
                        "timestamp_seconds": ts,
                        "source": video_path.name,
                        "frame_path": str(out_path.resolve()),
                    }
                )
                out_i += 1
            idx += 1
        return items, None
    finally:
        cap.release()


def extract_runtime_video_evidence(
    video_paths: List[Path],
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> Dict[str, Any]:
    """
    Sample frames from up to MAX_INPUT_VIDEOS videos into a temp directory
    named ``runtime_video_frames`` under a unique parent folder.

    Returns dict suitable for merging into profile ``runtime_evidence``.
    """
    videos = sorted({p.resolve() for p in video_paths if p.is_file()}, key=lambda x: str(x).lower())[
        :MAX_INPUT_VIDEOS
    ]
    if not videos:
        return {
            "video_metadata": {
                "duration_seconds": 0.0,
                "frame_count_extracted": 0,
                "sources": [],
            },
            "video_frame_count": 0,
            "video_evidence_items": [],
            "video_noise_flags": [],
            "video_extraction_errors": [],
            "video_extract_dir": None,
        }

    parent = Path(tempfile.mkdtemp(prefix="aigrader_video_"))
    frames_root = parent / "runtime_video_frames"
    frames_root.mkdir(parents=True, exist_ok=True)

    all_items: List[Dict[str, Any]] = []
    errors: List[str] = []
    sources_meta: List[Dict[str, Any]] = []
    duration_sum = 0.0

    for vp in videos:
        dur = _ffprobe_duration_seconds(vp)
        if dur is not None and dur > MAX_DURATION_SECONDS:
            errors.append(f"skip_long_video:{vp.name}")
            continue
        if dur is not None:
            duration_sum += min(dur, MAX_DURATION_SECONDS)

        budget = max(1, MAX_FRAMES_TOTAL - len(all_items))
        per_cap = min(MAX_FRAMES_PER_VIDEO, budget)
        if per_cap <= 0:
            break

        items: List[Dict[str, Any]] = []
        err: Optional[str] = None
        if shutil.which("ffmpeg"):
            items, err = _extract_frames_ffmpeg(vp, frames_root, interval_seconds, per_cap)
        if not items:
            items, err = _extract_frames_opencv(vp, frames_root, interval_seconds, per_cap)
        if err:
            errors.append(f"{vp.name}:{err}"[:400])
        all_items.extend(items)
        sources_meta.append(
            {
                "path": str(vp),
                "basename": vp.name,
                "duration_seconds": round(dur, 3) if dur is not None else None,
                "frames_extracted": len(items),
            }
        )

    noise: List[Dict[str, str]] = []
    if all_items and not shutil.which("ffmpeg") and not _has_opencv():
        noise.append({"flag": "video_frames_via_opencv_fallback"})
    if videos and not all_items:
        noise.append({"flag": "video_present_but_no_frames_extracted"})

    return {
        "video_metadata": {
            "duration_seconds": round(duration_sum, 3),
            "frame_count_extracted": len(all_items),
            "sources": sources_meta,
        },
        "video_frame_count": len(all_items),
        "video_evidence_items": all_items[:MAX_FRAMES_TOTAL],
        "video_noise_flags": noise,
        "video_extraction_errors": errors,
        "video_extract_dir": str(frames_root.resolve()),
    }


def _has_opencv() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def list_submission_video_files(file_paths: List[Path]) -> List[Path]:
    out: List[Path] = []
    for fp in file_paths:
        try:
            if fp.suffix.lower() in VIDEO_EXTENSIONS:
                out.append(fp)
        except (OSError, AttributeError):
            continue
    return sorted(set(out), key=lambda p: str(p).lower())
