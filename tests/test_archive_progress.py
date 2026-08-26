"""Archive listing/extract progress helpers."""
from pathlib import Path
import zipfile

from app.archive_extraction_utils import (
    _dedupe_code_scored,
    _source_code_pick_score,
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


def test_dedupe_preserves_same_named_events_for_different_gamemaker_objects():
    paths = [
        "Student/Project/التصميم/code/objects/obj_cat/Step_0.gml",
        "Student/Project/التصميم/code/objects/obj_mouse/Step_0.gml",
        "Student/Project/التطوير/code/M/objects/obj_cat/Step_0.gml",
        "Student/Project/التطوير/code/M/objects/obj_mouse/Step_0.gml",
    ]
    scored = [(_source_code_pick_score(path), path) for path in paths]

    out = _dedupe_code_scored(scored)
    selected = [path for _score, path in out]

    assert len(selected) == 2
    assert any("obj_cat/Step_0.gml" in path for path in selected)
    assert any("obj_mouse/Step_0.gml" in path for path in selected)
    assert all("/التطوير/" in path for path in selected)


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


def test_zip_keeps_all_aim_documents_and_both_gamemaker_versions(tmp_path: Path):
    from app.archive_extraction_utils import selective_extract_zip

    archive = tmp_path / "jana.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Jana/Aim B.docx", b"aim-b")
        zf.writestr("Jana/Aim C.docx", b"aim-c-larger")
        for version in ("V1", "V2"):
            base = f"Jana/Project/{version}"
            zf.writestr(f"{base}/CheeseChase.exe", b"MZ")
            zf.writestr(f"{base}/data.win", f"data-{version}".encode())
            zf.writestr(f"{base}/options.ini", b"[Windows]")

    extracted, _ = selective_extract_zip(
        str(archive),
        tmp_path / "out",
        skip_dir_names=frozenset(),
        gradable_extensions=(".docx", ".exe", ".win"),
        grading_mode="deep",
    )
    rels = {rel.replace("\\", "/") for rel, _ in extracted}

    assert "Jana/Aim B.docx" in rels
    assert "Jana/Aim C.docx" in rels
    assert "Jana/Project/V1/CheeseChase.exe" in rels
    assert "Jana/Project/V2/CheeseChase.exe" in rels
    assert "Jana/Project/V1/data.win" in rels
    assert "Jana/Project/V2/data.win" in rels


def test_zip_extract_keeps_each_gamemaker_object_event_and_prefers_development(tmp_path: Path):
    from app.archive_extraction_utils import selective_extract_zip

    archive = tmp_path / "gamemaker.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for stage in ("التصميم", "التطوير"):
            base = f"Jana/Project/{stage}/code/objects"
            zf.writestr(f"{base}/obj_mouse/Step_0.gml", f"// {stage} mouse")
            zf.writestr(f"{base}/obj_cheese/Step_0.gml", f"// {stage} cheese")
            zf.writestr(f"{base}/obj_game_ctrl/Create_0.gml", f"// {stage} controller")

    extracted, _ = selective_extract_zip(
        str(archive),
        tmp_path / "out",
        skip_dir_names=frozenset(),
        gradable_extensions=(".gml",),
        grading_mode="deep",
    )
    rels = {rel.replace("\\", "/") for rel, _path in extracted}

    assert len(rels) == 3
    assert all("/التطوير/" in rel for rel in rels)
    assert any("obj_mouse/Step_0.gml" in rel for rel in rels)
    assert any("obj_cheese/Step_0.gml" in rel for rel in rels)
    assert any("obj_game_ctrl/Create_0.gml" in rel for rel in rels)


def test_large_zip_does_not_apply_eight_file_cap_to_gamemaker_events(
    tmp_path: Path, monkeypatch
):
    import app.archive_extraction_utils as archive_utils

    archive = tmp_path / "large-gamemaker.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for index in range(12):
            zf.writestr(
                f"Student/Project/objects/obj_{index}/Step_0.gml",
                f"global.value_{index} += 1;",
            )
    real_getsize = archive_utils.os.path.getsize
    monkeypatch.setattr(
        archive_utils.os.path,
        "getsize",
        lambda path: 100 * 1024 * 1024 if str(path) == str(archive) else real_getsize(path),
    )

    extracted, _ = archive_utils.selective_extract_zip(
        str(archive),
        tmp_path / "out",
        skip_dir_names=frozenset(),
        gradable_extensions=(".gml",),
        grading_mode="deep",
    )

    assert len([rel for rel, _path in extracted if rel.endswith(".gml")]) == 12
