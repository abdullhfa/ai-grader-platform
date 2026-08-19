"""Tests for PRO GameMaker runtime verification."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from app.grading_mode_policy import deep_grading_flags, fast_grading_flags
from app.runtime_engines.gamemaker.object_inspection import inspect_gamemaker_objects
from app.runtime_engines.gamemaker.project_probe import (
    assess_gamemaker_exe_launch,
    materialize_gamemaker_runtime_assets,
    probe_gamemaker_layout,
    resolve_gamemaker_runtime_cwd,
)
from app.runtime_observation_sandbox import smoke_test_windows_exe
from app.runtime_engines.gamemaker.runtime_verification import _try_ide_build, run_build_pipeline
from app.runtime_engines.registry import resolve_engine


def test_runtime_outcome_is_labeled_gamemaker():
    from app.report_feedback_formatter import (
        build_runtime_outcome,
        ensure_runtime_outcome_engine,
        format_runtime_outcome_ar,
    )

    outcome = build_runtime_outcome(
        {"gameplay_entered": False, "l4_level": "L3"},
        {"criterion_pass": {}},
        engine_id="gamemaker",
    )
    assert outcome["engine_label_ar"] == "GameMaker"
    assert "GameMaker" in format_runtime_outcome_ar(outcome)
    assert ensure_runtime_outcome_engine({}, engine_id="gamemaker")["engine_label_ar"] == "GameMaker"


def test_gamemaker_default_plan_tests_top_down_mechanics_not_jump():
    from app.requirement_extractor import RequirementExtractor

    plan = RequirementExtractor().default_plan(engine="gamemaker")
    ids = plan.requirement_ids()
    assert "player_movement" in ids
    assert "collect_items" in ids
    assert "lives_system" in ids
    assert "score_system" in ids
    assert "win_lose_condition" in ids
    assert "enemy_interaction" in ids
    assert "timer_system" in ids
    assert "difficulty_levels" in ids
    assert "player_jump" not in ids
    movement = next(req for req in plan.requirements if req.req_id == "player_movement")
    assert movement.verification_method == "visual_player_movement"
    assert [(a.key, a.duration) for a in movement.input_sequence] == [("d", 1.5)]


def test_gamemaker_top_down_movement_uses_playfield_pixel_change(tmp_path: Path):
    from PIL import Image, ImageDraw

    from app.gameplay_verifier import RequirementVerifier

    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    first = Image.new("RGB", (200, 120), "black")
    draw = ImageDraw.Draw(first)
    draw.rectangle((20, 55, 39, 74), fill="white")
    first.save(before)
    second = Image.new("RGB", (200, 120), "black")
    draw = ImageDraw.Draw(second)
    draw.rectangle((70, 55, 89, 74), fill="white")
    second.save(after)

    verified, confidence, detail = RequirementVerifier().verify(
        "visual_player_movement",
        {"path": str(before)},
        {"path": str(after)},
        0.012,
        gameplay_entered=True,
    )

    assert verified is True
    assert confidence > 0
    assert "playfield_changed_ratio=" in detail


def test_menu_navigator_does_not_misclassify_gamemaker_level_select(monkeypatch):
    from app.gameplay_verifier import MenuNavigator

    monkeypatch.setattr(
        "app.gameplay_verifier._shot_ocr_text",
        lambda _shot: "CHEESE CHASE Easy - LV-1 Medium - LV-2 Arrow Keys to select",
    )
    shot = {"visual_state": "gameplay_candidate", "visual_stats": {"avg_luma_approx": 100}}
    assert MenuNavigator().classify_visual_state(shot) == "menu"


def test_menu_navigator_detects_gamemaker_export(tmp_path: Path):
    from app.gameplay_verifier import MenuNavigator

    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "data.win").write_bytes(b"runner")
    assert MenuNavigator._is_gamemaker_export(exe) is True


def test_menu_navigator_selects_gamemaker_level_with_keyboard(tmp_path: Path, monkeypatch):
    from app.gameplay_verifier import MenuNavigator

    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "data.win").write_bytes(b"runner")
    calls = []
    monkeypatch.setattr(
        "app.gameplay_verifier._send_key_win_legacy",
        lambda key, **_kwargs: calls.append(key) or True,
    )
    monkeypatch.setattr("app.gameplay_verifier.time.sleep", lambda _seconds: None)

    action = MenuNavigator()._dismiss_menu(
        shot={"game_window_bbox": [0, 0, 640, 480]},
        attempt=0,
        artifact_path=exe,
        process_pid=123,
    )

    assert action == "gamemaker_arrow_select_enter"
    assert calls == [0x28, 0x0D]


def test_menu_navigator_accepts_confirmed_gamemaker_scene_change(tmp_path: Path, monkeypatch):
    import random
    from PIL import Image, ImageChops
    from app.gameplay_verifier import MenuNavigator

    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "data.win").write_bytes(b"runner")
    menu = tmp_path / "menu.png"
    gameplay = tmp_path / "gameplay.png"
    rng = random.Random(42)
    menu_image = Image.new("RGB", (96, 72))
    menu_image.putdata(
        [(rng.randrange(30, 230), rng.randrange(30, 230), rng.randrange(30, 230)) for _ in range(96 * 72)]
    )
    menu_image.save(menu)
    ImageChops.offset(menu_image, 6, 0).save(gameplay)
    shots = iter((menu, menu, gameplay))

    monkeypatch.setattr("app.gameplay_verifier.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("app.gameplay_verifier._send_key_win_legacy", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("app.window_focus_manager.focus_game_window", lambda **_kwargs: True)
    monkeypatch.setattr(
        "app.gameplay_verifier.RequirementVerifier.verify_scene_change",
        lambda *_args, **_kwargs: (True, 0.42, "ssim_delta=0.420"),
    )

    def capture(*_args, **_kwargs):
        path = next(shots)
        return {
            "status": "captured",
            "path": str(path),
            "visual_state": "gameplay_candidate",
            "visual_stats": {"avg_luma_approx": 70},
            "capture_scope": "game_window",
            "game_window_detected": True,
            "game_window_bbox": [20, 30, 660, 510],
            "process_pid": 123,
        }

    result = MenuNavigator(max_attempts=3).navigate_to_gameplay(
        artifact_path=exe,
        process_pid=123,
        capture_screenshot=capture,
        elapsed_seconds=4.0,
    )

    assert result.gameplay_entered is True
    assert result.status == "gameplay_entered"
    assert result.visual_state == "gameplay"


def test_scene_change_uses_pillow_when_skimage_is_unavailable(tmp_path: Path):
    """Production does not install scikit-image; menu -> gameplay must still pass."""
    from PIL import Image

    from app.gameplay_verifier import RequirementVerifier

    menu = tmp_path / "menu.png"
    gameplay = tmp_path / "gameplay.png"
    Image.new("RGB", (100, 80), (15, 8, 5)).save(menu)
    image = Image.new("RGB", (100, 80), (15, 8, 5))
    for x in range(50):
        for y in range(80):
            image.putpixel((x, y), (115, 70, 25))
    image.save(gameplay)

    changed, delta, detail = RequirementVerifier().verify_scene_change(
        {"path": str(menu)},
        {"path": str(gameplay)},
        0.15,
    )

    assert changed is True
    assert delta > 0.15
    assert detail.startswith("pillow_changed_ratio=")


def test_gamemaker_menu_navigation_ignores_desktop_to_game_window_change(
    tmp_path: Path, monkeypatch
):
    """Regression: the grading page behind a late game window is not gameplay."""
    from PIL import Image

    from app.gameplay_verifier import MenuNavigator

    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "data.win").write_bytes(b"runner")
    desktop = tmp_path / "desktop.png"
    menu = tmp_path / "menu.png"
    gameplay = tmp_path / "gameplay.png"
    Image.new("RGB", (96, 72), (0, 80, 60)).save(desktop)
    Image.new("RGB", (96, 72), (90, 60, 35)).save(menu)
    Image.new("RGB", (96, 72), (180, 130, 30)).save(gameplay)

    shots = iter(
        (
            {
                "status": "captured",
                "path": str(desktop),
                "visual_state": "gameplay_candidate",
                "visual_stats": {"avg_luma_approx": 60},
                "capture_scope": "desktop_fallback",
                "game_window_detected": False,
                "process_pid": 123,
            },
            {
                "status": "captured",
                "path": str(menu),
                "visual_state": "gameplay_candidate",
                "visual_stats": {"avg_luma_approx": 45},
                "capture_scope": "game_window",
                "game_window_detected": True,
                "game_window_bbox": [20, 30, 660, 510],
                "process_pid": 123,
            },
            {
                "status": "captured",
                "path": str(menu),
                "visual_state": "gameplay_candidate",
                "visual_stats": {"avg_luma_approx": 45},
                "capture_scope": "game_window",
                "game_window_detected": True,
                "game_window_bbox": [20, 30, 660, 510],
                "process_pid": 123,
            },
            {
                "status": "captured",
                "path": str(gameplay),
                "visual_state": "gameplay_candidate",
                "visual_stats": {"avg_luma_approx": 85},
                "capture_scope": "game_window",
                "game_window_detected": True,
                "game_window_bbox": [20, 30, 660, 510],
                "process_pid": 123,
            },
        )
    )
    keys = []
    compared_scopes = []
    monkeypatch.setattr("app.gameplay_verifier.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.gameplay_verifier._send_key_win_legacy",
        lambda key, **_kwargs: keys.append(key) or True,
    )
    monkeypatch.setattr("app.window_focus_manager.focus_game_window", lambda **_kwargs: True)

    def verify_scene_change(_self, before, after, *_args, **_kwargs):
        compared_scopes.append((before.get("capture_scope"), after.get("capture_scope")))
        return True, 0.42, "ssim_delta=0.420"

    monkeypatch.setattr(
        "app.gameplay_verifier.RequirementVerifier.verify_scene_change",
        verify_scene_change,
    )

    result = MenuNavigator(max_attempts=3).navigate_to_gameplay(
        artifact_path=exe,
        process_pid=123,
        capture_screenshot=lambda *_args, **_kwargs: next(shots),
        elapsed_seconds=4.0,
    )

    assert result.gameplay_entered is True
    assert keys == [0x28, 0x0D]
    assert compared_scopes == [("game_window", "game_window")]


def test_pro_only_gamemaker_runtime_flag():
    assert fast_grading_flags("fast")["enable_gamemaker_runtime_verification"] is False
    assert deep_grading_flags("deep")["enable_gamemaker_runtime_verification"] is True


def test_gamemaker_engine_resolves(tmp_path: Path):
    (tmp_path / "Demo.yyp").write_text(
        '{"resourceType":"GMProject","resources":[{"id":{"name":"obj_player"},"resourceType":"GMObject"}]}',
        encoding="utf-8",
    )
    engine = resolve_engine(tmp_path)
    assert engine is not None
    assert engine.engine_id == "gamemaker"


def test_object_inspection_finds_objects_events(tmp_path: Path):
    (tmp_path / "Demo.yyp").write_text(
        '{"resourceType":"GMProject","resources":[{"id":{"name":"obj_player"},"resourceType":"GMObject"},{"id":{"name":"rm_main"},"resourceType":"GMRoom"}]}',
        encoding="utf-8",
    )
    obj = tmp_path / "objects" / "obj_player"
    obj.mkdir(parents=True)
    (obj / "Create_0.gml").write_text("x = 0;\n", encoding="utf-8")
    (tmp_path / "rooms" / "rm_main").mkdir(parents=True)

    layout = probe_gamemaker_layout(tmp_path / "Demo.yyp")
    inspection = inspect_gamemaker_objects(layout)
    assert inspection["inspection_ok"] is True
    assert inspection["summary"]["objects"] >= 1
    assert inspection["summary"]["events"] >= 1
    assert inspection["summary"]["rooms"] >= 1


def test_build_pipeline_yyp_ready(tmp_path: Path):
    yyp = tmp_path / "Demo.yyp"
    yyp.write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")
    layout = probe_gamemaker_layout(yyp)
    pipeline = run_build_pipeline(layout, workspace=tmp_path / "ws", timeout_seconds=5)
    assert pipeline["yyp_ready"] is True


def test_igor_build_runs_without_legacy_opt_in_flag(tmp_path: Path, monkeypatch):
    yyp = tmp_path / "Demo.yyp"
    yyp.write_text("{}", encoding="utf-8")
    runtime = tmp_path / "runtime-2024.11"
    igor = runtime / "bin" / "igor" / "windows" / "x64" / "Igor.exe"
    igor.parent.mkdir(parents=True)
    igor.write_bytes(b"MZ")
    user = tmp_path / "gm-user"
    user.mkdir()
    (user / "licence.plist").write_text("ready", encoding="utf-8")
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_IGOR", str(igor))
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_USER_FOLDER", str(user))
    monkeypatch.delenv("AI_GRADER_GAMEMAKER_IDE_BUILD", raising=False)

    def fake_run(cmd, **_kwargs):
        out_dir = Path(next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("/of=")))
        target = next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("/tf="))
        with zipfile.ZipFile(out_dir / target, "w") as zf:
            zf.writestr("Demo.exe", b"MZ")
            zf.writestr("data.win", b"game")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = _try_ide_build(yyp, tmp_path / "ws", timeout_seconds=5)
    assert out["attempted"] is True
    assert out["success"] is True
    assert Path(out["executable"]).is_file()
    assert out["command"][-3:] == ["--", "Windows", "PackageZip"]


def test_resolve_runtime_cwd_finds_parent_data_win(tmp_path: Path):
    v1 = tmp_path / "V1"
    project = v1 / "Project"
    project.mkdir(parents=True)
    (v1 / "data.win").write_bytes(b"win")
    exe = project / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    assert resolve_gamemaker_runtime_cwd(exe) == v1.resolve()


def test_assess_blocks_launch_without_data_win(tmp_path: Path):
    v1 = tmp_path / "V1" / "Project"
    v1.mkdir(parents=True)
    exe = v1 / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (v1 / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    (tmp_path / "Demo.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")

    assessment = assess_gamemaker_exe_launch(exe, search_root=tmp_path)
    assert assessment["is_gamemaker"] is True
    assert assessment["launch_allowed"] is False
    assert assessment["skip_reason"] == "missing_data_win"
    json.dumps(assessment)

    smoke = smoke_test_windows_exe(exe, session_ctx={"submission_root": str(tmp_path)})
    assert smoke["attempted"] is False
    assert smoke["smoke_result"] == "skipped_missing_data_win"


def test_materialize_data_win_from_upload_zip(tmp_path: Path):
    upload_dir = tmp_path / "batch_1_upload"
    upload_dir.mkdir()
    export = tmp_path / "student" / "V1"
    export.mkdir(parents=True)
    exe = export / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "student" / "CheeseChase.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")

    import zipfile

    zpath = upload_dir / "student.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("student/V1/data.win", b"win-bytes")
        zf.writestr("student/V1/options.ini", b"[Windows]\n")
        zf.writestr("student/V1/CheeseChase.exe", b"MZ")

    out = materialize_gamemaker_runtime_assets(exe, search_root=tmp_path / "student")
    assert out["materialized"] is True
    assert (export / "data.win").is_file()


def test_assess_finds_data_win_in_submission_tree(tmp_path: Path):
    export = tmp_path / "التصميم" / "V1"
    export.mkdir(parents=True)
    exe = export / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (export / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    assets = tmp_path / "bin"
    assets.mkdir()
    (assets / "data.win").write_bytes(b"win")
    (tmp_path / "CheeseChase.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")

    assessment = assess_gamemaker_exe_launch(exe, search_root=tmp_path)
    assert assessment["launch_allowed"] is True
    assert assessment["staged"] is True
    assert assessment["data_win_source_path"] == str((assets / "data.win").resolve())
    assert Path(assessment["runtime_executable"]).is_file()
    json.dumps(assessment)
    shutil.rmtree(assessment["cleanup_runtime_dir"], ignore_errors=True)


def test_assess_stages_newest_gamemaker_data_version(tmp_path: Path):
    v1 = tmp_path / "التصميم" / "V1"
    v2 = tmp_path / "التطوير" / "V2"
    v1.mkdir(parents=True)
    v2.mkdir(parents=True)
    exe = v1 / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (v1 / "data.win").write_bytes(b"old")
    (v1 / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    (v2 / "data.win").write_bytes(b"new-runtime")

    assessment = assess_gamemaker_exe_launch(exe, search_root=tmp_path)

    assert assessment["launch_allowed"] is True
    assert assessment["staged"] is True
    assert assessment["data_win_source_path"] == str((v2 / "data.win").resolve())
    stage = Path(assessment["runtime_cwd"])
    assert (stage / "CheeseChase.exe").read_bytes() == b"MZ"
    assert (stage / "data.win").read_bytes() == b"new-runtime"
    assert (stage / "options.ini").is_file()
    shutil.rmtree(stage, ignore_errors=True)


def test_probe_prefers_v2_and_never_borrows_other_students_exe(tmp_path: Path):
    student_a = tmp_path / "student-a"
    v1 = student_a / "V1"
    v2 = student_a / "V2"
    v1.mkdir(parents=True)
    v2.mkdir(parents=True)
    (v1 / "Game.yyp").write_text("{\"v\":1}", encoding="utf-8")
    (v2 / "Game.yyp").write_text("{\"v\":2}", encoding="utf-8")
    other = tmp_path / "student-b"
    other.mkdir()
    (other / "Game.exe").write_bytes(b"MZ")
    (other / "data.win").write_bytes(b"other")

    layout = probe_gamemaker_layout(student_a)

    assert layout.yyp_path == (v2 / "Game.yyp")
    assert layout.executable is None
    assert layout.version_evidence["v1_present"] is True
    assert layout.version_evidence["v2_present"] is True
    assert layout.version_evidence["updated_version_differs"] is True


def test_gamemaker_bitmap_hud_is_gameplay_and_timer_does_not_fake_score(tmp_path: Path, monkeypatch):
    from PIL import Image, ImageDraw

    from app.gameplay_verifier import MenuNavigator, RequirementVerifier

    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    before = Image.new("RGB", (800, 600), "black")
    draw = ImageDraw.Draw(before)
    draw.rectangle((20, 25, 95, 65), fill=(230, 30, 30))
    draw.rectangle((160, 25, 430, 65), fill=(230, 190, 20))
    draw.rectangle((675, 25, 770, 65), fill=(230, 190, 20))
    for x in range(40, 760, 120):
        draw.rectangle((x, 170, x + 55, 260), fill=(100, 60, 35))
    before.save(before_path)
    after = before.copy()
    ImageDraw.Draw(after).rectangle((740, 25, 770, 65), fill=(20, 20, 20))
    after.save(after_path)
    monkeypatch.setattr("app.gameplay_verifier._shot_ocr_text", lambda _shot: "")

    before_shot = {"path": str(before_path), "visual_state": "gameplay_candidate"}
    after_shot = {"path": str(after_path), "visual_state": "gameplay_candidate"}
    assert MenuNavigator().classify_visual_state(before_shot) == "gameplay"
    verifier = RequirementVerifier()
    timer_ok, _, _ = verifier.verify_timer_region_change(before_shot, after_shot, 0.0)
    score_ok, _, _ = verifier.verify_score_region_change(before_shot, after_shot, 0.0)
    assert timer_ok is True
    assert score_ok is False


def test_runtime_capture_reuses_known_game_window_bbox():
    from app import runtime_observation_sandbox as sandbox

    sandbox._GAME_WINDOW_BBOX_CACHE.clear()
    bbox = (10, 20, 650, 500)
    sandbox._remember_game_window_bbox(12345, bbox)
    assert sandbox._cached_game_window_bbox(12345) == bbox
    assert sandbox._cached_game_window_bbox(99999) is None


def test_gamemaker_l4_full_ai_certifies_cm3_and_cd3_without_human_review():
    from app.runtime_evidence_gate import BTECCriterionMapper

    def academic_row(level: str, reasoning: str) -> dict:
        return {
            "criteria_level": level,
            "achieved": False,
            "missing_points": [],
            "covered_points": ["دليل موثق مرتبط بالمهمة"],
            "decision_matrix": [
                {
                    "requirement": level,
                    "met": False,  # stale runtime hold must not erase the AI evidence
                    "evidence": "سجل اختبار وتحسينات موثقة ونتائج فعلية للنموذج الأولي",
                    "reasoning": reasoning,
                }
            ],
            "deterministic_rubric": {
                "deterministic_achieved": True,
                "verdict_status": "pass",
                "authority": "RUNTIME_VALIDATION",
                "evidence_registry": {
                    "visual_evidence": {
                        "authority": {"authority_sufficient": True}
                    }
                },
            },
        }

    rows = [
        academic_row(
            "C.M3",
            "عرض تقني منظم وفعال يشرح الاختبار والتحسين بناء على الملاحظات.",
        ),
        academic_row(
            "C.D3",
            "عرض مقنع شامل يتضمن تحليلاً نقدياً وبيانات وتبريراً استراتيجياً.",
        ),
    ]
    gv = {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "player_movement_verified": True,
        "mechanics_verified_count": 4,
        "gameplay_window_screenshots": 17,
        "evidence_package": {
            "results": [
                {"req_id": "player_movement", "verified": True},
                {"req_id": "enemy_interaction", "verified": True},
                {"req_id": "lives_system", "verified": True},
                {"req_id": "win_lose_condition", "verified": True},
            ]
        },
    }

    result = BTECCriterionMapper().evaluate(
        gv,
        test_doc_entries=1,
        functional_smoke_pass=True,
        criteria_results=rows,
        engine_id="gamemaker",
    )

    assert result["criterion_pass"]["M3"] is True
    assert result["criterion_pass"]["D3"] is True
    decisions = {row["criterion"]: row for row in result["decisions"]}
    assert decisions["M3"]["automatic"] is True
    assert decisions["D3"]["automatic"] is True
    assert decisions["M3"]["teacher_confirmation_required"] is False
    assert decisions["D3"]["teacher_confirmation_required"] is False
    assert decisions["M3"]["ai_academic_verified"] is True
    assert decisions["D3"]["ai_verification_confidence"] == 1.0


def test_terminal_runtime_gate_promotes_gamemaker_higher_bands_with_ai(monkeypatch):
    from app.runtime_evidence_gate import apply_runtime_evidence_gate

    def row(level: str, reasoning: str = "") -> dict:
        result = {
            "criteria_level": level,
            "achieved": level in {"C.P5", "C.P6"},
            "score": 75 if level in {"C.P5", "C.P6"} else 35,
            "missing_points": [],
            "covered_points": ["سجل أداء واختبار موثق"],
            "decision_matrix": [
                {
                    "requirement": level,
                    "met": level in {"C.P5", "C.P6"},
                    "evidence": "نتائج اختبار وتحسينات وبيانات موثقة",
                    "reasoning": reasoning or "تم تحقيق المعيار",
                }
            ],
        }
        if level in {"C.M3", "C.D3"}:
            result["achievement_authority"] = "HUMAN_REVIEW_REQUIRED"
            result["deterministic_rubric"] = {
                "deterministic_achieved": True,
                "verdict_status": "pass",
                "authority": "RUNTIME_VALIDATION",
                "evidence_registry": {
                    "visual_evidence": {
                        "authority": {"authority_sufficient": True}
                    }
                },
            }
        return result

    grading = {
        "grading_mode": "deep",
        "criteria_results": [
            row("C.P5"),
            row("C.P6"),
            row("C.M3", "عرض تقني منظم وفعال مع اختبار وتحسين وملاحظات."),
            row("C.D3", "عرض مقنع وشامل وتحليل نقدي وبيانات وتبرير استراتيجي."),
        ],
        "intake_relative_paths": ["Aim C.docx", "CheeseChase.exe"],
    }
    gv = {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "player_movement_verified": True,
        "mechanics_verified_count": 4,
        "gameplay_window_screenshots": 17,
    }
    inventory = {
        "runtime_artifacts": {"gamemaker_detected": True},
        "gameplay_verification": gv,
        "testing_evidence": {"status": "present", "entries": [{"test": "gameplay"}]},
        "assets_detected": {"word_pdf": True},
    }
    grading["artifact_inventory"] = inventory
    monkeypatch.setattr(
        "app.runtime_evidence_gate.evaluate_runtime_evidence",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "satisfied": True,
            "accepted_evidence": ["automated_l4_full"],
            "engine_id": "gamemaker",
            "summary_ar": "تحقق L4 آلي",
        },
    )

    report = apply_runtime_evidence_gate(grading, artifact_inventory=inventory)

    by_level = {item["criteria_level"]: item for item in grading["criteria_results"]}
    for level in ("C.M3", "C.D3"):
        assert by_level[level]["achieved"] is True
        assert by_level[level]["achievement_authority"] == "AI_RUNTIME_COMPOSITE"
        assert by_level[level]["ai_verification"]["human_review_required"] is False
        assert "مراجعة بشرية" not in by_level[level]["feedback"]
    assert report["automated_l4_gate"]["criterion_pass"]["M3"] is True
    assert report["automated_l4_gate"]["criterion_pass"]["D3"] is True
