"""BASIC video keyframe vision tuples must use real MIME types."""
from __future__ import annotations

import zipfile
from pathlib import Path

from app.academic_explainability import _media_verification_present, _submission_has_video
from app.basic_video_keyframes import (
    _discover_videos_on_disk,
    _list_videos_in_archive,
    _load_vision_bytes,
    _mime_for_frame,
    format_basic_video_keyframes_status_ar,
    merge_basic_vision_images,
)
from app.project_intelligence.video_runtime_extractor import _timestamp_for_percentile


def test_mime_for_frame_png():
    assert _mime_for_frame(Path("frame.png")) == "image/png"


def test_load_vision_bytes_uses_image_mime_not_filename(tmp_path: Path):
    fp = tmp_path / "فيديو اللعبة_pct000.png"
    fp.write_bytes(b"\x89PNG" + b"x" * 600)
    images = _load_vision_bytes([fp])
    assert len(images) == 1
    assert images[0][1] == "image/png"
    assert images[0][1].startswith("image/")


def test_discover_videos_on_disk_recursive(tmp_path: Path):
    (tmp_path / "gameplay.mp4").write_bytes(b"\x00" * 2048)
    nested = tmp_path / "clips"
    nested.mkdir()
    (nested / "level1.mov").write_bytes(b"\x00" * 2048)
    found = _discover_videos_on_disk(tmp_path)
    names = {p.name.lower() for p in found}
    assert "gameplay.mp4" in names
    assert "level1.mov" in names


def test_list_videos_in_archive_zip(tmp_path: Path):
    zpath = tmp_path / "sub.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("student/game.mp4", b"\x00" * 2048)
        zf.writestr("student/report.docx", b"doc")
    rels = _list_videos_in_archive(str(zpath))
    assert any(r.endswith("game.mp4") for r in rels)


def test_format_basic_video_keyframes_status_ar():
    assert "5 إطار/فيديو" in format_basic_video_keyframes_status_ar(
        {"videos_found": 2, "frames_extracted": 10, "frames_per_video": 5}
    )


def test_merge_basic_vision_unlimited_word():
    word = [(b"w", f"w{i}") for i in range(1, 21)]
    video = [(b"v", f"v{i}") for i in range(1, 6)]
    merged, stats = merge_basic_vision_images(word, video, max_word=0, max_video=5)
    assert stats["word_images"] == 20
    assert stats["video_keyframes"] == 5
    assert len(merged) == 25


def test_merge_basic_vision_separate_caps():
    word = [(b"w", f"w{i}") for i in range(1, 11)]
    video = [(b"v", f"v{i}") for i in range(1, 6)]
    merged, stats = merge_basic_vision_images(word, video, max_word=10, max_video=5)
    assert stats["word_images"] == 10
    assert stats["video_keyframes"] == 5
    assert stats["total_vision"] == 15
    assert len(merged) == 15


def test_timestamp_percentiles():
    assert _timestamp_for_percentile(100.0, 0.0) == 0.0
    assert _timestamp_for_percentile(100.0, 0.5) == 50.0
    assert _timestamp_for_percentile(100.0, 1.0) == 99.85


def test_basic_media_verification_with_keyframes():
    inv = {
        "visual_evidence_summary": {
            "images_analyzed": 10,
            "video_keyframes_found": 1,
            "video_keyframes_analyzed": 5,
        },
        "basic_video_keyframes_meta": {
            "videos_found": 1,
            "frames_extracted": 5,
            "frames_per_video": 5,
        },
        "vision_analysis_used": True,
        "intake_relative_paths": ["gameplay.mp4"],
        "runtime_observation_report": {"status": "skipped_fast_mode"},
    }
    assert _submission_has_video(inv) is True
    ok, status = _media_verification_present(inv, has_screenshots=True, grading_mode="fast")
    assert ok is True
    assert "عدد الفيديوهات :" in status
