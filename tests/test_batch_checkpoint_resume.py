"""Checkpoint resume after server restart."""
from pathlib import Path

from app.batch_checkpoint import (
    batch_has_extracted_student_work,
    batch_is_resumable_after_restart,
    restore_paused_checkpoint_files,
)


def test_restore_paused_checkpoint_renames_file(tmp_path, monkeypatch):
    ck_dir = tmp_path / "checkpoints"
    ck_dir.mkdir()
    paused = ck_dir / "batch_42.json.paused"
    paused.write_text('{"batch_id": 42}', encoding="utf-8")
    monkeypatch.setattr("app.batch_checkpoint._CHECKPOINT_DIR", ck_dir)
    assert restore_paused_checkpoint_files() == 1
    assert (ck_dir / "batch_42.json").is_file()
    assert not paused.is_file()


def test_batch_is_resumable_with_checkpoint(tmp_path, monkeypatch):
    ck_dir = tmp_path / "checkpoints"
    ck_dir.mkdir()
    (ck_dir / "batch_7.json").write_text(
        '{"batch_id": 7, "student_files": [{"name": "a", "path": "/x"}]}',
        encoding="utf-8",
    )
    students = tmp_path / "students"
    students.mkdir()
    monkeypatch.setattr("app.batch_checkpoint._CHECKPOINT_DIR", ck_dir)
    monkeypatch.setattr("app.batch_checkpoint.STUDENTS_DIR", students)
    assert batch_is_resumable_after_restart(7) is True


def test_batch_has_extracted_student_work(tmp_path, monkeypatch):
    students = tmp_path / "students"
    bx = students / "bx9"
    bx.mkdir(parents=True)
    (bx / "student.docx").write_bytes(b"x")
    monkeypatch.setattr("app.batch_checkpoint.STUDENTS_DIR", students)
    assert batch_has_extracted_student_work(9) is True


def test_should_supersede_single_student_lock():
    import time

    from app.batch_grade_worker import should_supersede_assignment_lock

    now = time.time()
    active = {"finished": False, "total": 1, "current_phase": "starting", "start_time": now}
    assert should_supersede_assignment_lock(
        active, single_student_archive=False, force_regrade=False
    )
    assert should_supersede_assignment_lock(
        active, single_student_archive=True, force_regrade=False
    )
    multi = {"finished": False, "total": 5, "current_phase": "grading", "start_time": now}
    assert not should_supersede_assignment_lock(
        multi, single_student_archive=True, force_regrade=False
    )
    assert should_supersede_assignment_lock(
        multi, single_student_archive=False, force_regrade=True
    )


def test_progress_is_stuck_idle_starting(monkeypatch):
    from app.batch_grade_worker import _progress_is_stuck

    monkeypatch.setattr("app.batch_grade_worker.time.time", lambda: 2000.0)
    info = {
        "finished": False,
        "current_phase": "starting",
        "start_time": 100.0,
    }
    assert _progress_is_stuck(info) is True
