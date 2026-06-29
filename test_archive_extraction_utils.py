"""Archive single-student bundle detection — regression for category-folder false positives."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.archive_extraction_utils import (
    _member_worth_indexing,
    archive_extract_timeout_seconds,
    archive_list_timeout_seconds,
    archive_should_use_selective_extract,
    consolidate_archive_student_results,
    count_distinct_archive_students,
    force_single_student_archive_result,
    max_archive_extract_files,
    path_has_ignored_segment,
    pick_best_submission_file,
    reject_single_mode_for_multi_student_archive,
)
from app.project_intelligence.submission_intake import INTAKE_IGNORE_DIR_NAMES


def _row(name: str, path: str = "/tmp/x.docx", arc: str | None = None) -> tuple:
    arc = arc or f"{name}/report.docx"
    return (name, path, [path], [arc])


def test_category_folders_count_as_one_student():
    result = [
        _row("وثائق", arc="وثائق/report.docx"),
        _row("اللعبة", arc="اللعبة/game.exe"),
        _row("فيديو", arc="فيديو/demo.mp4"),
        _row("استبيان", arc="استبيان/form.pdf"),
    ]
    assert count_distinct_archive_students(result) == 1
    assert reject_single_mode_for_multi_student_archive(
        result, archive_name="عبدالله العتوم.rar"
    ) is None


def test_unity_build_folders_count_as_one_student():
    result = [
        _row("MyGame", arc="MyGame/MyGame.exe"),
        _row("MyGame_Data", arc="MyGame_Data/level0"),
        _row("MonoBleedingEdge", arc="MonoBleedingEdge/EmbedRuntime"),
        _row("وثائق", arc="وثائق/report.docx"),
    ]
    assert count_distinct_archive_students(result) == 1
    assert reject_single_mode_for_multi_student_archive(result) is None


def test_multiple_tf_folders_still_rejected():
    result = [
        _row("Ahmad TF(11111)", arc="Ahmad TF(11111)/a.docx"),
        _row("Sara TF(22222)", arc="Sara TF(22222)/b.docx"),
    ]
    assert count_distinct_archive_students(result) == 2
    reject = reject_single_mode_for_multi_student_archive(result)
    assert reject is not None
    assert reject["code"] == "multi_student_archive_in_single_mode"


def test_force_merge_uses_archive_filename():
    result = [
        _row("وثائق"),
        _row("اللعبة"),
    ]
    merged = force_single_student_archive_result(
        result, archive_name="عبدالله العتوم.rar"
    )
    assert len(merged) == 1
    assert merged[0][0] == "عبدالله العتوم"


def test_unity_build_bundle_merges_to_one():
    result = [
        _row("My project (3)", arc="My project (3)/Assets/GameStart.cs"),
        _row("My project (3)_Data", arc="My project (3)_Data/globalgamemanagers"),
        _row("MonoBleedingEdge", arc="MonoBleedingEdge/etc/mono/config"),
        _row("My project (3)", path="/tmp/My project (3).exe", arc="My project (3).exe"),
    ]
    from app.archive_extraction_utils import merge_likely_single_student_bundle

    merged = merge_likely_single_student_bundle(
        result,
        top_level_folder_names={
            "My project (3)",
            "My project (3)_Data",
            "MonoBleedingEdge",
        },
        archive_name="عبدالله العتوم.rar",
    )
    assert len(merged) == 1
    assert merged[0][0] == "عبدالله العتوم"
    assert reject_single_mode_for_multi_student_archive(result) is None

    result = [
        _row("وثائق"),
        _row("game build"),
        _row("video clips"),
    ]
    consolidated = consolidate_archive_student_results(result)
    assert len(consolidated) == 1


def test_pick_best_prefers_game_exe_over_browscap():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        browscap = root / "MonoBleedingEdge" / "etc" / "mono" / "browscap.ini"
        browscap.parent.mkdir(parents=True)
        browscap.write_text("x" * 500_000, encoding="utf-8")
        game_exe = root / "My project (3).exe"
        game_exe.write_bytes(b"MZ" + b"\0" * 1000)
        crash = root / "UnityCrashHandler64.exe"
        crash.write_bytes(b"MZ" + b"\0" * 2000)

        rows = [
            ("MonoBleedingEdge", str(browscap)),
            ("__root__", str(game_exe)),
            ("__root__", str(crash)),
        ]
        picked = pick_best_submission_file(rows)
        assert picked is not None
        assert picked[1] == str(game_exe)


def test_merge_bundle_primary_is_game_exe():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        browscap = root / "MonoBleedingEdge" / "etc" / "mono" / "browscap.ini"
        browscap.parent.mkdir(parents=True)
        browscap.write_text("ini", encoding="utf-8")
        game_exe = root / "My project (3).exe"
        game_exe.write_bytes(b"MZ" + b"\0" * 500)
        cs = root / "My project (3)" / "Assets" / "GameStart.cs"
        cs.parent.mkdir(parents=True)
        cs.write_text("class GameStart {}", encoding="utf-8")

        result = [
            ("MonoBleedingEdge", str(browscap), [str(browscap)], ["MonoBleedingEdge/etc/mono/browscap.ini"]),
            ("My project (3)", str(cs), [str(cs), str(game_exe)], ["My project (3)/Assets/GameStart.cs", "My project (3).exe"]),
        ]
        from app.archive_extraction_utils import merge_likely_single_student_bundle

        merged = merge_likely_single_student_bundle(
            result,
            top_level_folder_names={"MonoBleedingEdge", "My project (3)"},
            archive_name="عبدالله العتوم.rar",
        )
        assert len(merged) == 1
        assert merged[0][0] == "عبدالله العتوم"
        assert merged[0][1] == str(game_exe)


def test_godot_editor_exe_not_primary_game_executable():
    from app.archive_extraction_utils import is_primary_game_executable

    assert not is_primary_game_executable("أدوات التصدير/Godot_v4.6-stable_win64.exe")
    assert not is_primary_game_executable("tools/Godot_v4.6-stable_win64.exe")
    assert is_primary_game_executable("MyGame/MyGame.exe")


def test_pro_archives_always_use_selective_extract():
    assert archive_should_use_selective_extract(50, 1024, "deep") is True
    assert archive_should_use_selective_extract(10, 1024, "deep") is True
    assert max_archive_extract_files("deep") in (60, 100)
    assert max_archive_extract_files("deep", archive_bytes=90 * 1024 * 1024) in (36, 100)
    assert max_archive_extract_files("fast") == 200


def test_archive_timeouts_scale_for_large_uploads():
    assert archive_list_timeout_seconds(50 * 1024 * 1024) >= 120
    assert archive_extract_timeout_seconds("deep") >= 2400
    assert archive_extract_timeout_seconds("fast") == 1200


def test_build_folder_ignored_in_rar_indexing():
    assert path_has_ignored_segment("game/_build/cache.bin", INTAKE_IGNORE_DIR_NAMES)


def test_member_worth_indexing_skips_godot_import_noise():
    assert not _member_worth_indexing(
        "proj/icon.png.import",
        skip_extract_ext=frozenset({".import", ".png"}),
        gradable_extensions=(".gd",),
        should_skip_extract=lambda _p: False,
    )
    assert _member_worth_indexing(
        "proj/main.gd",
        skip_extract_ext=frozenset({".import", ".png"}),
        gradable_extensions=(".gd",),
        should_skip_extract=lambda _p: False,
    )


def test_materialize_nested_zip_game_executables_unpacks_exe():
    import zipfile

    from app.archive_extraction_utils import materialize_nested_zip_game_executables

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        student = root / "واجب"
        student.mkdir()
        inner_exe = b"MZ-fake-game-exe"
        inner_zip_path = student / "(.exe)بعد التعديل.zip"
        with zipfile.ZipFile(inner_zip_path, "w") as zf:
            zf.writestr("build/MemoryGame.exe", inner_exe)
            zf.writestr("build/data.win", b"data")
            zf.writestr("build/options.ini", b"ini")

        out = materialize_nested_zip_game_executables(root, grading_mode="deep")
        assert len(out) == 3
        exe_disk = student / "_nested_runtime" / "(.exe)بعد التعديل" / "MemoryGame.exe"
        assert exe_disk.is_file()
        assert exe_disk.read_bytes() == inner_exe
        assert (student / "_nested_runtime" / "(.exe)بعد التعديل" / "data.win").is_file()


def test_materialize_nested_zip_skips_when_loose_exe_exists():
    import zipfile

    from app.archive_extraction_utils import materialize_nested_zip_game_executables

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        student = root / "Jana"
        runtime = student / "V1"
        runtime.mkdir(parents=True)
        (runtime / "CheeseChase.exe").write_bytes(b"MZ-loose")
        inner_zip = student / "bundle.zip"
        with zipfile.ZipFile(inner_zip, "w") as zf:
            zf.writestr("other/OtherGame.exe", b"MZ-other")

        out = materialize_nested_zip_game_executables(root, grading_mode="deep")
        assert out == []
        assert not (student / "_nested_runtime").exists()
