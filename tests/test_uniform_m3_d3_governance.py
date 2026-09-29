"""Regression tests: uniform M3/D3 governance, V1→V2 code-diff gate, executable discovery.

Covers the governance bug where GameMaker could reach Merit/Distinction from
``documented improvement regex + L4`` while Unity/Godot/Scratch could not, and the
discovery gap that hid executables inside ``bin/`` and ``obj/``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime_evidence_gate import BTECCriterionMapper, apply_runtime_evidence_gate
from app.version_code_diff import (
    discover_version_groups,
    evaluate_m3_code_diff,
    extract_improvement_claims,
)

ENGINES = ("gamemaker", "unity", "godot", "scratch")

FULL_L4 = {
    "gameplay_entered": True,
    "l4_level": "L4_full",
    "player_movement_verified": True,
    "mechanics_verified_count": 4,
    "gameplay_window_screenshots": 12,
}

SUPPORTED_DIFF = {
    "evaluated": True,
    "ok": True,
    "status": "supported",
    "substantive_change_count": 3,
    "claims_total": 2,
    "supported_claims": 2,
}


def _academic_row(level: str) -> dict:
    return {
        "criteria_level": level,
        "achieved": False,
        "score": 35,
        "covered_points": ["تحسين واختبار وملاحظات منظم وفعال"],
        "missing_points": [],
        "decision_matrix": [
            {
                "requirement": level,
                "met": False,
                "evidence": "جدول تحسينات ونتائج اختبار",
                "reasoning": "عرض تقني منظم وفعال مقنع شامل مع نقد وتبرير استراتيجي وبيانات ونسب.",
            }
        ],
        "deterministic_rubric": {
            "deterministic_achieved": True,
            "verdict_status": "pass",
            "authority": "DETERMINISTIC",
            "rule_id": "bc_d3_self_management" if level.endswith("D3") else "merit_analysis",
        },
    }


def _evaluate(engine: str, *, confirmed=None, code_diff=None, **kw):
    return BTECCriterionMapper().evaluate(
        dict(FULL_L4),
        test_doc_entries=2,
        functional_smoke_pass=True,
        teacher_confirmed=confirmed,
        criteria_results=[_academic_row("C.M3"), _academic_row("C.D3")],
        engine_id=engine,
        student_text="قمت بتحسين سرعة الفأر وإضافة حماية مؤقتة بعد الاختبار. " * 20,
        code_diff=code_diff,
        **kw,
    )


# ── 1. GameMaker exception removed ───────────────────────────────────────────
@pytest.mark.parametrize("engine", ENGINES)
def test_m3_and_d3_never_open_automatically_on_any_engine(engine):
    result = _evaluate(engine)
    assert result["criterion_pass"]["M3"] is False
    assert result["criterion_pass"]["D3"] is False
    by = {d["criterion"]: d for d in result["decisions"]}
    for key in ("M3", "D3"):
        assert by[key]["automatic"] is False
        assert by[key]["teacher_confirmation_required"] is True
        assert by[key]["reason"] == "teacher_confirmation_required"


def test_gamemaker_m3_does_not_pass_automatically():
    result = _evaluate("gamemaker", code_diff=SUPPORTED_DIFF)
    assert result["criterion_pass"]["M3"] is False
    assert result["higher_band_verification"] == "policy_default"


def test_gamemaker_d3_does_not_pass_automatically():
    result = _evaluate("gamemaker", code_diff=SUPPORTED_DIFF)
    assert result["criterion_pass"]["D3"] is False


def test_gamemaker_decisions_are_identical_to_other_engines():
    def shape(engine):
        result = _evaluate(engine, confirmed={"M3": True, "D3": True}, code_diff=SUPPORTED_DIFF)
        return (
            result["criterion_pass"],
            [(d["criterion"], d["open"], d["automatic"], d["teacher_confirmation_required"]) for d in result["decisions"]],
        )

    baseline = shape("unity")
    for engine in ("gamemaker", "godot", "scratch"):
        assert shape(engine) == baseline


def test_gamemaker_m3_needs_full_l4_like_other_engines():
    partial = dict(FULL_L4, l4_level="L4_partial")
    result = BTECCriterionMapper().evaluate(
        partial,
        test_doc_entries=2,
        functional_smoke_pass=True,
        teacher_confirmed={"M3": True},
        criteria_results=[_academic_row("C.M3")],
        engine_id="gamemaker",
        code_diff=SUPPORTED_DIFF,
    )
    assert result["criterion_pass"]["M3"] is False


# ── 2. Code-diff gate for M3 ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "diff",
    [
        None,
        {"evaluated": True, "ok": False, "status": "versions_not_found"},
        {"evaluated": True, "ok": False, "status": "no_code_change"},
        {"evaluated": True, "ok": False, "status": "improvements_mostly_unsupported"},
    ],
)
def test_m3_is_blocked_without_v1_v2_code_evidence(diff):
    result = _evaluate("gamemaker", confirmed={"M3": True, "D3": True}, code_diff=diff)
    assert result["criterion_pass"]["M3"] is False
    m3 = next(d for d in result["decisions"] if d["criterion"] == "M3")
    assert m3["reason"].startswith("m3_code_diff_")
    assert any(c.startswith("m3_code_diff=") for c in m3["evidence_chain"])
    # Distinction can never outrun a blocked Merit.
    assert result["criterion_pass"]["D3"] is False


@pytest.mark.parametrize("engine", ENGINES)
def test_m3_with_documented_code_diff_and_runtime_passes_to_assessment(engine):
    result = _evaluate(engine, confirmed={"M3": True}, code_diff=SUPPORTED_DIFF)
    assert result["criterion_pass"]["M3"] is True
    m3 = next(d for d in result["decisions"] if d["criterion"] == "M3")
    assert m3["reason"] == "teacher_confirmation_required"  # human confirmation still recorded
    assert "m3_code_diff=supported" in m3["evidence_chain"]


def test_m3_with_code_diff_but_without_runtime_stays_closed():
    result = BTECCriterionMapper().evaluate(
        {"gameplay_entered": False, "l4_level": "L3"},
        test_doc_entries=2,
        teacher_confirmed={"M3": True},
        criteria_results=[_academic_row("C.M3")],
        engine_id="gamemaker",
        code_diff=SUPPORTED_DIFF,
    )
    assert result["criterion_pass"]["M3"] is False


def test_d3_needs_m3_even_when_confirmed():
    blocked = _evaluate("unity", confirmed={"D3": True}, code_diff=None)
    assert blocked["criterion_pass"]["D3"] is False
    opened = _evaluate("unity", confirmed={"M3": True, "D3": True}, code_diff=SUPPORTED_DIFF)
    assert opened["criterion_pass"]["M3"] is True
    assert opened["criterion_pass"]["D3"] is True


# ── code-diff engine (real files) ────────────────────────────────────────────
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _gamemaker_versions(tmp: Path, *, v2_step: str, v2_extra: dict | None = None) -> Path:
    """Jana-like layout: build folders V1/V2 sit NEXT to the project folders."""
    root = tmp / "student"
    for design, ver, step, code_dir in (
        ("Design", "V1", "spd = 4; // move\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n", "code"),
        ("Dev", "V2", v2_step, "code/M"),
    ):
        base = root / design
        (base / ver).mkdir(parents=True)
        (base / ver / "splash.png").write_bytes(b"png")  # build folder: image only
        (base / ver / "Game.exe").write_bytes(b"MZ")
        _write(base / code_dir / "Game.yyp", "{}")
        _write(base / code_dir / "objects/obj_mouse/Step_0.gml", step)
        _write(base / code_dir / "objects/obj_cat/Create_0.gml", "move_spd = 3;\n")
    for rel, text in (v2_extra or {}).items():
        _write(root / "Dev/code/M" / rel, text)
    return root


def test_version_discovery_handles_build_folders_next_to_project_folders(tmp_path):
    root = _gamemaker_versions(tmp_path, v2_step="spd = 6;\n")
    groups = discover_version_groups(root)
    assert groups["status"] == "ok"
    assert groups["v1"]["project_root"].name == "code"
    assert groups["v2"]["project_root"].name == "M"


def test_supported_improvement_claim_is_linked_to_a_real_change(tmp_path):
    root = _gamemaker_versions(tmp_path, v2_step="spd = 6;\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n")
    report = evaluate_m3_code_diff(
        [], "بعد الاختبار قمت بزيادة سرعة الفأر spd في كود التحكم.", root=root
    )
    assert report["ok"] is True
    assert report["status"] == "supported"
    claim = next(c for c in report["claims"] if c["id"] == "movement_speed")
    assert claim["supported"] is True
    assert claim["evidence"][0]["path"].endswith("obj_mouse/Step_0.gml")


def test_claim_without_a_code_change_stays_unsupported_and_blocks_m3(tmp_path):
    # V2 changes speed, but the student ALSO claims invincibility/audio/tutorial work
    # that never happened → mostly unsupported.
    root = _gamemaker_versions(tmp_path, v2_step="spd = 6;\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n")
    text = (
        "قمت بتحسين سرعة الفأر spd. اضفت حماية مؤقتة invincible مع وميض. "
        "قمت بضغط الصوت وتحسين الاداء delta time. اضفت غرفة تعليمية tutorial."
    )
    report = evaluate_m3_code_diff([], text, root=root)
    by_id = {c["id"]: c for c in report["claims"]}
    assert by_id["movement_speed"]["supported"] is True
    assert by_id["invincibility"]["supported"] is False
    assert by_id["tutorial"]["supported"] is False
    assert report["ok"] is False
    assert report["status"] == "improvements_mostly_unsupported"
    assert "الحماية المؤقتة/الوميض" in report["unsupported_claims"]


def test_comment_and_whitespace_only_changes_are_not_improvements(tmp_path):
    root = _gamemaker_versions(
        tmp_path,
        v2_step="spd   =   4;   /* faster? */\n// new comment\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n",
    )
    report = evaluate_m3_code_diff([], "قمت بتحسين سرعة الفأر spd.", root=root)
    assert report["ok"] is False
    assert report["status"] == "no_code_change"
    assert report["substantive_change_count"] == 0


def test_claim_already_present_in_v1_is_not_counted_as_an_improvement(tmp_path):
    # Invincibility exists in BOTH versions → not in the diff → unsupported.
    root = tmp_path / "student"
    for design, ver, extra in (("D1", "V1", ""), ("D2", "V2", "hard = 1;\n")):
        _write(root / design / "code/Game.yyp", "{}")
        _write(root / design / "code/o/Step_0.gml", "invincible = 120;\n" + extra)
        (root / design / ver).mkdir(parents=True)
        (root / design / ver / "Game.exe").write_bytes(b"MZ")
    report = evaluate_m3_code_diff([], "اضفت حماية مؤقتة invincible مع وميض بعد الاستبيان.", root=root)
    claim = next(c for c in report["claims"] if c["id"] == "invincibility")
    assert claim["supported"] is False
    assert report["ok"] is False


def test_symlinks_out_of_the_submission_are_never_read(tmp_path):
    secret = tmp_path / "secret.gml"
    secret.write_text("invincible = 999;\n", encoding="utf-8")
    root = tmp_path / "student"
    for design, ver, extra in (("D1", "V1", ""), ("D2", "V2", "hard = 1;\n")):
        _write(root / design / "code/Game.yyp", "{}")
        _write(root / design / "code/o/Step_0.gml", "spd = 4;\n" + extra)
        (root / design / ver).mkdir(parents=True)
    try:
        (root / "D2" / "code" / "o" / "leak.gml").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    report = evaluate_m3_code_diff([], "اضفت حماية مؤقتة invincible مع وميض.", root=root)
    assert all("leak.gml" not in c["path"] for c in report.get("changed_files", []))
    assert all(not c["supported"] for c in report.get("claims", []))


def test_future_plans_are_not_counted_as_claims():
    claims = extract_improvement_claims("سأعمل في التحديث القادم على تحسين سرعة الفأر وإضافة الصوت.")
    assert claims == []


def test_single_version_or_ambiguous_layout_never_opens_m3(tmp_path):
    root = tmp_path / "student"
    _write(root / "code/Game.yyp", "{}")
    _write(root / "code/o/Step_0.gml", "spd = 4;\n")
    assert evaluate_m3_code_diff([], "قمت بتحسين سرعة الفأر spd.", root=root)["ok"] is False

    both = tmp_path / "s2"
    for ver in ("V1", "V2"):
        _write(both / ver / "Game.yyp", "{}")
    # V1/V2 nested inside each other's group root → not separable, never guessed.
    (both / "V1" / "V2").mkdir()
    assert evaluate_m3_code_diff([], "x", root=both)["status"] in {
        "versions_not_separable", "no_code_change", "versions_not_found"
    }


# ── integration through the terminal gate ────────────────────────────────────
def _gate_result(tmp_path: Path, monkeypatch, student_text: str, root: Path, teacher=None):
    rows = [
        {**_academic_row("C.P5"), "achieved": True, "score": 75},
        {**_academic_row("C.P6"), "achieved": True, "score": 75},
        {**_academic_row("C.M3"), "achieved": True, "score": 85},
    ]
    doc = root / "Aim C.docx"
    doc.write_bytes(b"docx")
    inventory = {
        "runtime_artifacts": {"gamemaker_detected": True},
        "gameplay_verification": dict(FULL_L4),
        "testing_evidence": {"status": "present", "entries": [{"t": 1}, {"t": 2}]},
        "assets_detected": {"word_pdf": True},
        "l5_human_playtest": {"status": "complete_visual"},
    }
    grading = {
        "grading_mode": "deep",
        "criteria_results": rows,
        "artifact_inventory": inventory,
        "student_text": student_text,
        "submission_paths": [str(doc)],
        "intake_relative_paths": ["Aim C.docx"],
    }
    if teacher:
        from app.runtime_evidence_gate import record_teacher_confirmation

        for key in teacher:
            record_teacher_confirmation(grading, key, confirmed_by="reviewer", note="checked V1→V2")
    monkeypatch.setattr(
        "app.runtime_evidence_gate.evaluate_runtime_evidence",
        lambda *_a, **_k: {
            "status": "PASS", "satisfied": True, "accepted_evidence": ["automated_l4_full"],
            "engine_id": "gamemaker", "summary_ar": "ok",
        },
    )
    report = apply_runtime_evidence_gate(grading, artifact_inventory=inventory)
    return grading, report, {r["criteria_level"]: r for r in grading["criteria_results"]}


def test_terminal_gate_blocks_m3_when_improvements_are_unsupported(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step="spd = 6;\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n")
    text = (
        "قمت بتحسين سرعة الفأر spd. اضفت حماية مؤقتة invincible مع وميض. "
        "قمت بضغط الصوت وتحسين الاداء delta time. اضفت غرفة تعليمية tutorial."
    )
    grading, report, by = _gate_result(tmp_path, monkeypatch, text, root)
    assert by["C.M3"]["achieved"] is False
    assert report["automated_l4_gate"]["criterion_pass"]["M3"] is False
    assert report["m3_code_diff"]["status"] == "improvements_mostly_unsupported"


def test_terminal_gate_opens_m3_only_with_supported_code_diff_and_explicit_teacher_confirmation(
    tmp_path, monkeypatch
):
    from app.runtime_evidence_gate import record_teacher_confirmation

    root = _gamemaker_versions(tmp_path, v2_step="spd = 6;\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n")
    grading, report, by = _gate_result(
        tmp_path, monkeypatch, "بعد الاختبار قمت بزيادة سرعة الفأر spd في كود التحكم.", root,
        teacher={"M3": True},
    )
    assert report["m3_code_diff"]["ok"] is True
    assert by["C.M3"]["achieved"] is True
    assert by["C.M3"]["achievement_authority"] == "HUMAN_CONFIRMED_RUNTIME_GATE"
    assert by["C.M3"]["ai_verification"]["automatic"] is False
    assert grading["teacher_confirmations"]["M3"]["confirmed_by"] == "reviewer"
    assert callable(record_teacher_confirmation)


# ── 3. Executable discovery ──────────────────────────────────────────────────
def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "student"
    root.mkdir()
    (root / "Report.docx").write_bytes(b"docx")
    return root


def _expand(root: Path, seeds=None):
    from app.evidence_completeness_gate import expand_submission_paths

    seeds = seeds or [str(root / "Report.docx")]
    return [Path(p).as_posix() for p in expand_submission_paths(seeds, primary_path=seeds[0])]


def test_exe_inside_bin_is_discovered(tmp_path):
    root = _tree(tmp_path)
    (root / "bin" / "Release").mkdir(parents=True)
    (root / "bin" / "Release" / "Game.exe").write_bytes(b"MZ")
    assert any(p.endswith("bin/Release/Game.exe") for p in _expand(root))


def test_exe_inside_obj_is_discovered(tmp_path):
    root = _tree(tmp_path)
    (root / "obj").mkdir()
    (root / "obj" / "Game.exe").write_bytes(b"MZ")
    assert any(p.endswith("obj/Game.exe") for p in _expand(root))


def test_non_executable_files_inside_bin_and_obj_stay_ignored(tmp_path):
    root = _tree(tmp_path)
    (root / "bin").mkdir()
    (root / "bin" / "helper.js").write_text("x", encoding="utf-8")
    (root / "obj").mkdir()
    (root / "obj" / "cache.cs").write_text("x", encoding="utf-8")
    found = _expand(root)
    assert not any("/bin/" in p or "/obj/" in p for p in found)


def test_junk_executables_inside_bin_stay_ignored(tmp_path):
    root = _tree(tmp_path)
    (root / "bin").mkdir()
    (root / "bin" / "UnityCrashHandler64.exe").write_bytes(b"MZ")
    (root / "bin" / "Game.exe").write_bytes(b"MZ")
    found = _expand(root)
    assert any(p.endswith("bin/Game.exe") for p in found)
    assert not any("UnityCrashHandler" in p for p in found)


def test_engine_cache_folders_stay_ignored_even_for_exe(tmp_path):
    root = _tree(tmp_path)
    (root / "Library").mkdir()
    (root / "Library" / "Cached.exe").write_bytes(b"MZ")
    assert not any("/Library/" in p for p in _expand(root))


def test_large_submissions_do_not_lose_the_executable(tmp_path):
    root = _tree(tmp_path)
    assets = root / "Assets"
    assets.mkdir()
    for i in range(650):  # well above the generic 400-file budget
        (assets / f"img_{i:04d}.png").write_bytes(b"p")
    (root / "zz_last").mkdir()
    (root / "zz_last" / "Game.exe").write_bytes(b"MZ")
    (root / "bin").mkdir()
    (root / "bin" / "Final.exe").write_bytes(b"MZ")
    found = _expand(root)
    assert any(p.endswith("zz_last/Game.exe") for p in found)
    assert any(p.endswith("bin/Final.exe") for p in found)


def test_already_rich_path_list_does_not_hide_a_second_build(tmp_path):
    root = _tree(tmp_path)
    for name in ("a.gml", "b.gml", "c.gml"):
        (root / name).write_text("x", encoding="utf-8")
    (root / "V1.exe").write_bytes(b"MZ")
    (root / "bin").mkdir()
    (root / "bin" / "V2.exe").write_bytes(b"MZ")
    seeds = [str(root / n) for n in ("a.gml", "b.gml", "c.gml", "V1.exe")]
    assert any(p.endswith("bin/V2.exe") for p in _expand(root, seeds))


def test_intake_ignore_uses_the_file_not_only_the_folder_name():
    from app.project_intelligence.submission_intake import path_matches_intake_ignore

    assert path_matches_intake_ignore("student/bin/Release/Game.exe") is False
    assert path_matches_intake_ignore("student/obj/Game.exe") is False
    assert path_matches_intake_ignore("student/Builds/Windows/Game.exe") is False
    assert path_matches_intake_ignore("student/bin/data.win") is False
    assert path_matches_intake_ignore("student/bin/cache.bin") is True
    assert path_matches_intake_ignore("student/bin/helper.dll") is True
    assert path_matches_intake_ignore("student/Library/Game.exe") is True
    assert path_matches_intake_ignore("student/node_modules/x/Game.exe") is True
    assert path_matches_intake_ignore("student/bin/UnityCrashHandler64.exe") is True


def test_archive_extraction_filter_keeps_build_executables():
    from app.archive_extraction_utils import path_has_ignored_segment
    from app.project_intelligence.submission_intake import INTAKE_IGNORE_DIR_NAMES

    assert path_has_ignored_segment("game/bin/Game.exe", INTAKE_IGNORE_DIR_NAMES) is False
    assert path_has_ignored_segment("game/obj/Game.exe", INTAKE_IGNORE_DIR_NAMES) is False
    assert path_has_ignored_segment("game/_build/cache.bin", INTAKE_IGNORE_DIR_NAMES) is True
    assert path_has_ignored_segment("game/Library/Game.exe", INTAKE_IGNORE_DIR_NAMES) is True
