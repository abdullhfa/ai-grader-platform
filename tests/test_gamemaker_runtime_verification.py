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
    win_lose = next(req for req in plan.requirements if req.req_id == "win_lose_condition")
    wait_seconds = sum(a.duration for a in win_lose.input_sequence if a.action == "wait")
    assert wait_seconds <= 5.0, "GameMaker win/lose must not idle ~35s after gameplay is already visible"


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


def test_gamemaker_l4_full_and_academic_evidence_do_not_open_cm3_or_cd3():
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

    # Uniform governance: GameMaker gets no AI/regex shortcut to Merit or Distinction.
    # L4_full runtime + academic text alone never open M3/D3 — M3 also needs a provable
    # V1→V2 code diff (none was supplied here), and D3 needs M3.  Fully automated:
    # nothing waits on a human, the gate is simply closed (NOT_VERIFIED).
    assert result["criterion_pass"]["M3"] is False
    assert result["criterion_pass"]["D3"] is False
    decisions = {row["criterion"]: row for row in result["decisions"]}
    assert decisions["M3"]["automatic"] is True
    assert decisions["D3"]["automatic"] is True
    assert "teacher_confirmation_required" not in decisions["M3"]
    assert decisions["M3"]["reason"] == "m3_code_diff_not_evaluated"
    assert decisions["D3"]["reason"] == "prerequisite_m3_not_met"
    # The academic assessment stays visible in the report, but only as advice.
    assert decisions["M3"]["ai_academic_verified"] is True
    assert result["higher_band_verification"] == "policy_default"


def test_terminal_runtime_gate_does_not_promote_gamemaker_higher_bands_with_ai(monkeypatch):
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
    # Same policy as every other engine: no AI composite promotion to Merit.
    assert by_level["C.M3"]["achieved"] is False
    assert by_level["C.M3"].get("achievement_authority") != "AI_RUNTIME_COMPOSITE"
    assert by_level["C.D3"]["achieved"] is False
    assert report["automated_l4_gate"]["criterion_pass"]["M3"] is False
    assert report["automated_l4_gate"]["criterion_pass"]["D3"] is False


def test_probe_ignores_stale_generated_runtime_as_student_exe(tmp_path: Path):
    from app.runtime_engines.gamemaker.project_probe import GENERATED_RUNTIME_DIRNAME

    student = tmp_path / "student"
    generated = student / GENERATED_RUNTIME_DIRNAME
    generated.mkdir(parents=True)
    (student / "Game.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")
    (generated / "Game.exe").write_bytes(b"MZ")
    (generated / "data.win").write_bytes(b"win")

    layout = probe_gamemaker_layout(student)

    assert layout.executable is None
    assert layout.yyp_path == student / "Game.yyp"


def test_windows_exe_smoke_runs_without_sandbox_env_flag(tmp_path: Path, monkeypatch):
    from app.runtime_engines.base import RuntimeSession
    from app.runtime_engines.gamemaker.runtime_runner import run_exe_smoke

    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "data.win").write_bytes(b"win")
    (tmp_path / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    (tmp_path / "Game.yyp").write_text('{"resourceType":"GMProject"}', encoding="utf-8")
    called = {}

    def fake_smoke(*_args, **kwargs):
        called["kwargs"] = kwargs
        return {
            "attempted": True,
            "smoke_result": "stable_window",
            "runtime_screenshots": [{"path": str(tmp_path / "shot.png")}],
            "signals": {"crash": "none"},
            "visual_observation": {"freeze_possible": False},
        }

    monkeypatch.delenv("AI_GRADER_WINDOWS_SANDBOX", raising=False)
    monkeypatch.setattr("app.runtime_engines.gamemaker.runtime_runner.sys.platform", "win32")
    monkeypatch.setattr(
        "app.runtime_observation_sandbox.smoke_test_windows_exe",
        fake_smoke,
    )
    (tmp_path / "shot.png").write_bytes(b"png")
    session = RuntimeSession.create("gamemaker", "jana-exe", tmp_path)
    out = run_exe_smoke(session, exe, timeout_seconds=8)

    assert out.get("skipped") is not True
    assert called, "existing student exe must reach smoke_test_windows_exe on Windows"
    assert session.signals.get("runtime_method") == "gamemaker_exe_smoke"


def test_existing_student_exe_is_launched_and_never_deleted(tmp_path: Path, monkeypatch):
    from app.runtime_engines.base import RuntimeSession
    from app.runtime_engines.gamemaker.runtime_verification import (
        run_gamemaker_runtime_verification,
    )

    student = tmp_path / "student"
    student.mkdir()
    exe = student / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (student / "data.win").write_bytes(b"win")
    (student / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    (student / "Game.yyp").write_text(
        '{"resourceType":"GMProject","resources":[{"id":{"name":"obj_player"},"resourceType":"GMObject"}]}',
        encoding="utf-8",
    )
    (student / "objects" / "obj_player").mkdir(parents=True)
    (student / "objects" / "obj_player" / "Step_0.gml").write_text(
        "keyboard_check(vk_right);", encoding="utf-8"
    )
    launched: list[Path] = []

    def fake_smoke(session, executable, **_kwargs):
        launched.append(Path(executable))
        session.screenshot_paths.append(tmp_path / "shot.png")
        (tmp_path / "shot.png").write_bytes(b"png")
        session.signals["runtime_method"] = "gamemaker_exe_smoke"
        return {"success": True, "observation": {"status": "completed"}}

    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.runtime_verification.run_exe_smoke",
        fake_smoke,
    )
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.runtime_verification._try_ide_build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not build when exe exists")),
    )
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.runtime_verification.compare_runtime_screenshots",
        lambda shots: {
            "comparison_available": True,
            "freeze_detected": False,
            "frame_delta_score": 0.4,
        },
    )

    session = RuntimeSession.create("gamemaker", "has-exe", student, workspace=tmp_path / "ws")
    layout = probe_gamemaker_layout(student)
    result = run_gamemaker_runtime_verification(session, layout, timeout_seconds=5)

    assert [path.resolve() for path in launched] == [exe.resolve()]
    assert exe.is_file()
    assert (student / "data.win").is_file()
    assert not (student / "_ai_grader_gm_runtime").exists()
    assert result["build_pipeline"]["ide_build_attempted"] is False
    assert result["build_pipeline"].get("student_runtime", {}).get("generated") is not True
    assert result["gameplay_replay"]["method"] == "exe_smoke"
    assert result["signals"]["functional_smoke_pass"] is True


def test_missing_exe_is_built_into_student_folder_then_removed(tmp_path: Path, monkeypatch):
    from app.runtime_engines.base import RuntimeSession
    from app.runtime_engines.gamemaker.runtime_verification import (
        run_gamemaker_runtime_verification,
    )

    student = tmp_path / "student"
    student.mkdir()
    yyp = student / "Game.yyp"
    yyp.write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")
    (student / "player.gml").write_text("keyboard_check(vk_right);", encoding="utf-8")
    seen: dict = {}

    def fake_run(cmd, **_kwargs):
        out_dir = Path(next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("/of=")))
        target = next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("/tf="))
        with zipfile.ZipFile(out_dir / target, "w") as zf:
            zf.writestr("CheeseChase.exe", b"MZ")
            zf.writestr("data.win", b"built-win")
            zf.writestr("options.ini", b"[Windows]\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_smoke(session, executable, **_kwargs):
        exe = Path(executable)
        seen["exe"] = exe
        seen["exists_during_run"] = exe.is_file()
        seen["inside_student"] = student.resolve() in exe.resolve().parents
        seen["data_win"] = (exe.parent / "data.win").is_file()
        session.screenshot_paths.append(tmp_path / "shot.png")
        (tmp_path / "shot.png").write_bytes(b"png")
        session.signals["runtime_method"] = "gamemaker_exe_smoke"
        return {"success": True, "observation": {"status": "completed"}}

    monkeypatch.setenv("AI_GRADER_GAMEMAKER_IGOR", str(tmp_path / "Igor.exe"))
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_USER_FOLDER", str(tmp_path / "user"))
    (tmp_path / "Igor.exe").write_bytes(b"MZ")
    (tmp_path / "runtime").mkdir()
    (tmp_path / "user").mkdir()
    (tmp_path / "user" / "licence.plist").write_text("ready", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.runtime_verification.run_exe_smoke",
        fake_smoke,
    )
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.runtime_verification.compare_runtime_screenshots",
        lambda shots: {
            "comparison_available": True,
            "freeze_detected": False,
            "frame_delta_score": 0.4,
        },
    )

    session = RuntimeSession.create("gamemaker", "no-exe", student, workspace=tmp_path / "ws")
    layout = probe_gamemaker_layout(student)
    assert layout.executable is None
    result = run_gamemaker_runtime_verification(session, layout, timeout_seconds=5)

    assert seen["exists_during_run"] is True
    assert seen["inside_student"] is True
    assert seen["data_win"] is True
    assert seen["exe"].name.endswith(".exe")
    assert not (student / "_ai_grader_gm_runtime").exists()
    assert list(student.rglob("*.exe")) == []
    assert result["build_pipeline"]["ide_build_attempted"] is True
    assert result["build_pipeline"]["student_runtime"]["generated"] is True
    assert result["signals"]["generated_runtime_cleanup"]["cleaned"] is True
    assert result["gameplay_replay"]["method"] == "exe_smoke"
    assert result["signals"]["functional_smoke_pass"] is True
