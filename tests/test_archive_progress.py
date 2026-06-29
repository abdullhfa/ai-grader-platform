"""Archive listing/extract progress helpers."""
from app.archive_extraction_utils import (
    _dedupe_code_scored,
    archive_ui_percent,
    max_archive_code_files_per_group,
)


def test_archive_ui_percent_listing_moves_past_25_cap():
    assert archive_ui_percent(phase="listing", listed=0) == 8
    assert archive_ui_percent(phase="listing", listed=200) == 18
    assert archive_ui_percent(phase="extract", frac=1.0) == 45
    assert archive_ui_percent(phase="extract", frac=0.0) == 20


def test_dedupe_code_scored_keeps_one_gd_per_basename():
    scored = [
        ((2, -100), "before/main.gd"),
        ((2, -200), "after/main.gd"),
    ]
    out = _dedupe_code_scored(scored)
    assert len(out) == 1
    assert out[0][1].endswith("after/main.gd")


def test_large_archive_lowers_code_cap():
    assert max_archive_code_files_per_group("deep", 250 * 1024 * 1024) == 6
    assert max_archive_code_files_per_group("deep", 10 * 1024 * 1024) == 16


def test_pro_skips_heavy_exe_when_godot_bundle_indexed():
    from app.grading_mode_policy import pro_should_skip_game_exe_disk_extract

    paths = ["P_03.exe", "P_03.pck", "main.gd", "project.godot"]
    assert pro_should_skip_game_exe_disk_extract(
        "P_03.exe", group_paths=paths, member_size=200_000_000, grading_mode="deep"
    )
    assert not pro_should_skip_game_exe_disk_extract(
        "P_03.exe", group_paths=paths, member_size=200_000_000, grading_mode="fast"
    )
    assert not pro_should_skip_game_exe_disk_extract(
        "P_03.exe", group_paths=["main.gd", "game.pck"], member_size=200_000_000, grading_mode="deep"
    )
    assert not pro_should_skip_game_exe_disk_extract(
        "small.exe", group_paths=paths, member_size=40 * 1024 * 1024, grading_mode="deep"
    )


def test_sync_progress_percent_bumps_when_all_students_done():
    from app.batch_grade_worker import _sync_progress_percent

    info = {
        "total": 1,
        "completed": 1,
        "student_progress": 0.0,
        "current_phase": "saving",
        "percent": 12,
        "finished": False,
    }
    _sync_progress_percent(info)
    assert info["percent"] >= 99


def test_sync_progress_percent_never_drops_pro_grading_floor():
    from app.batch_grade_worker import _sync_progress_percent

    info = {
        "total": 1,
        "completed": 0,
        "student_progress": 0.08,
        "current_phase": "grading",
        "percent": 46,
        "grading_mode": "deep",
        "archive_all_files": ["main.gd"],
    }
    _sync_progress_percent(info)
    assert info["percent"] >= 46


def test_archive_extract_sort_key_puts_exe_last():
    from app.archive_extraction_utils import _archive_extract_sort_key

    names = sorted(
        ["P_03.exe", "report.docx", "main.gd"],
        key=_archive_extract_sort_key,
    )
    assert names[-1] == "P_03.exe"
    assert names[0] == "report.docx"
