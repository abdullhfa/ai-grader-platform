from pathlib import Path

from PIL import Image, ImageDraw

from app.gameplay_verifier import PlaytestOrchestrator, RequirementResult


def _shot(path: Path, *, terminal: bool) -> dict:
    image = Image.new("RGB", (800, 600), "black")
    draw = ImageDraw.Draw(image)
    if terminal:
        draw.rectangle((220, 170, 580, 250), fill=(240, 30, 30))
    else:
        draw.rectangle((30, 30, 70, 70), fill=(255, 255, 0))
    image.save(path)
    return {"path": str(path), "status": "captured", "capture_scope": "game_window"}


def test_stateful_gameover_evidence_repairs_later_identical_pairs(tmp_path):
    student = tmp_path / "uploads" / "students" / "b1" / "student"
    exe = student / "Project" / "V2" / "game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    code = student / "Project" / "source" / "controller.gml"
    code.parent.mkdir(parents=True)
    code.write_text(
        '''
        var ch = instance_place(x, y, obj_cheese);
        global.score += 10;
        global.cheese_collected++;
        instance_destroy(ch);
        draw_text(0,0,"Score: " + string(global.score));
        global.lives -= 1;
        draw_text(0,0,string(global.lives) + " hearts");
        if (place_meeting(x, y, obj_cat)) global.lives -= 1;
        draw_text(0,0,"Avoid cats! Each collision costs a life");
        global.time_left -= 1; alarm[0] = room_speed;
        if (global.time_left <= 0) global.phase = "gameover";
        if (global.phase == "gameover") draw_text(0,0,"GAME OVER");
        if (global.cheese_collected >= global.cheese_total) global.phase = "win";
        if (global.phase == "win") draw_text(0,0,"YOU WIN! All cheese collected");
        draw_text(0,0,"Enter = Play Again");
        if (keyboard_check_pressed(vk_enter)) room_restart();
        ''',
        encoding="utf-8",
    )
    gameplay = _shot(tmp_path / "gameplay.png", terminal=False)
    terminal = _shot(tmp_path / "terminal.png", terminal=True)
    rows = [
        RequirementResult(req_id="score_system", verified=False, before_screenshot=gameplay, after_screenshot=gameplay),
        RequirementResult(req_id="enemy_interaction", verified=False, before_screenshot=terminal, after_screenshot=terminal),
        RequirementResult(req_id="lives_system", verified=False, before_screenshot=terminal, after_screenshot=terminal),
        RequirementResult(req_id="timer_system", verified=False, before_screenshot=terminal, after_screenshot=terminal),
        RequirementResult(req_id="win_lose_condition", verified=False, before_screenshot=terminal, after_screenshot=terminal),
        RequirementResult(req_id="difficulty_levels", verified=True, before_screenshot=terminal, after_screenshot=gameplay),
    ]

    PlaytestOrchestrator._reconcile_cross_modal_results(
        artifact_path=exe,
        results=rows,
        screenshots=[gameplay, terminal],
        gameplay_entered=True,
    )

    by_id = {row.req_id: row for row in rows}
    for req_id in (
        "collect_items",
        "score_system",
        "enemy_interaction",
        "lives_system",
        "timer_system",
        "win_condition",
        "lose_condition",
        "win_lose_condition",
        "restart",
    ):
        assert by_id[req_id].verified is True
        assert by_id[req_id].verification_basis == "source_runtime_corroboration"


def test_source_claims_without_runtime_terminal_do_not_get_promoted(tmp_path):
    student = tmp_path / "uploads" / "students" / "b1" / "student"
    exe = student / "Project" / "V2" / "game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    code = student / "controller.gml"
    code.write_text('global.score = 10; draw_text(0,0,"Score:");', encoding="utf-8")
    gameplay = _shot(tmp_path / "gameplay.png", terminal=False)
    rows = [RequirementResult(req_id="score_system", verified=False)]
    PlaytestOrchestrator._reconcile_cross_modal_results(
        artifact_path=exe,
        results=rows,
        screenshots=[gameplay],
        gameplay_entered=True,
    )
    assert rows[0].verified is False


def test_decorative_hud_and_terminal_text_are_not_complete_code_proof(tmp_path):
    student = tmp_path / "uploads" / "students" / "b1" / "student"
    exe = student / "game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    (student / "draw.gml").write_text(
        '''
        draw_text(0, 0, "Score: " + string(global.score));
        if (global.phase == "win") draw_text(0, 0, "YOU WIN! All cheese collected");
        if (global.phase == "gameover") draw_text(0, 0, "GAME OVER");
        draw_text(0, 0, "Enter = Play Again");
        ''',
        encoding="utf-8",
    )

    signals = PlaytestOrchestrator._source_feature_signals(exe)

    assert signals["score_system"] is False
    assert signals["win_condition"] is False
    assert signals["lose_condition"] is False
    assert signals["restart"] is False


def test_start_game_full_reset_is_recognised_as_restart_implementation(tmp_path):
    student = tmp_path / "uploads" / "students" / "b1" / "student"
    exe = student / "Project" / "V2" / "game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    code = student / "Project" / "source" / "controller.gml"
    code.parent.mkdir(parents=True)
    code.write_text(
        '''
        start_game = function() {
            global.score = 0;
            global.cheese_collected = 0;
            global.lives = 3;
            global.time_left = 60;
            global.phase = "countdown";
        }
        if (global.phase == "gameover" || global.phase == "win") {
            draw_text(0, 0, "Enter = Play Again");
            if (keyboard_check_pressed(vk_enter)) start_game();
        }
        ''',
        encoding="utf-8",
    )

    signals = PlaytestOrchestrator._source_feature_signals(exe)

    assert signals["restart"] is True
