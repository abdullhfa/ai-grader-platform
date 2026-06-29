"""Per-student video workspace isolation in BASIC keyframe extraction."""
from __future__ import annotations

from pathlib import Path

from app.basic_video_keyframes import (
    _path_under_workspace,
    _rel_belongs_to_student_intake,
    _resolve_submission_workspace,
)


def test_rel_belongs_rejects_other_student_folder(tmp_path: Path):
    workspace = tmp_path / "student_a"
    workspace.mkdir()
    assert _rel_belongs_to_student_intake("student_a/report.docx", workspace) is True
    assert _rel_belongs_to_student_intake("student_b/gameplay.mp4", workspace) is False


def test_path_under_workspace(tmp_path: Path):
    workspace = tmp_path / "student_a"
    workspace.mkdir()
    inside = workspace / "clip.mp4"
    inside.write_bytes(b"\x00" * 64)
    outside = tmp_path / "student_b" / "clip.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"\x00" * 64)
    assert _path_under_workspace(inside, workspace) is True
    assert _path_under_workspace(outside, workspace) is False


def test_workspace_root_from_primary_doc(tmp_path: Path):
    student_root = tmp_path / "student_a"
    student_root.mkdir()
    doc = student_root / "report.docx"
    doc.write_bytes(b"doc")
    ws = _resolve_submission_workspace(str(doc), [str(doc)], student_name="Student A")
    assert ws.resolve() == student_root.resolve()
