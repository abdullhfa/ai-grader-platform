"""Tests for evidence completeness pre-gate."""
from __future__ import annotations

from pathlib import Path

from app.evidence_completeness_gate import (
    evaluate_evidence_completeness,
    expand_submission_paths,
    resolve_student_submission_root,
)
from app.governance_freeze_registry import is_l4_sandbox_permitted


def test_resolve_student_root_from_assets_path(tmp_path):
    student = tmp_path / "عبدالله"
    student.mkdir()
    (student / "game.exe").write_bytes(b"x" * 10)
    assets = student / "My project" / "Assets"
    assets.mkdir(parents=True)
    cs = assets / "Player.cs"
    cs.write_text("class Player {}", encoding="utf-8")
    root = resolve_student_submission_root(str(cs), student_name="عبدالله")
    assert root == student


def test_expand_submission_paths_includes_exe(tmp_path):
    student = tmp_path / "student"
    student.mkdir()
    exe = student / "game.exe"
    exe.write_bytes(b"x" * 10)
    assets = student / "Assets"
    assets.mkdir()
    cs = assets / "A.cs"
    cs.write_text("x", encoding="utf-8")
    paths = expand_submission_paths([str(cs)], primary_path=str(cs), student_name="student")
    assert any(p.endswith("game.exe") for p in paths)
    assert any(p.endswith("A.cs") for p in paths)


def test_evidence_gate_flags_missing_gdd(tmp_path):
    criteria = [
        {
            "criteria_level": "8/B.P3",
            "criteria_name": "GDD",
            "criteria_description": "إعداد وثيقة تصميم لعبة GDD",
            "key_points": [],
        },
        {
            "criteria_level": "8/C.P5",
            "criteria_name": "Produce game",
            "criteria_description": "إنتاج لعبة حاسوب مع الكود",
            "key_points": [],
        },
    ]
    cs = tmp_path / "Player.cs"
    cs.write_text("class X {}", encoding="utf-8")
    code_only = [str(cs)]
    report = evaluate_evidence_completeness(
        grading_criteria=criteria,
        submission_paths=code_only,
        primary_path=code_only[0],
    )
    p3 = next(r for r in report["per_criterion"] if "P3" in r["criteria_level"])
    assert not p3["satisfied"]
    assert "gdd_document" in p3["missing_artifacts"]
    p5 = next(r for r in report["per_criterion"] if "P5" in r["criteria_level"])
    assert "executable" in p5["missing_artifacts"]


def test_godot_bundle_without_gdpc_magic_counts_as_source(tmp_path):
    root = tmp_path / "student"
    root.mkdir()
    (root / "game.pck").write_bytes(b"not-a-real-pck-but-present")
    (root / "game.exe").write_bytes(b"MZ" + b"\0" * 20)
    from app.evidence_completeness_gate import evaluate_evidence_completeness

    report = evaluate_evidence_completeness(
        grading_criteria=[
            {
                "criteria_level": "8/C.P5",
                "criteria_description": "إنتاج لعبة حاسوب",
                "key_points": [],
            }
        ],
        submission_paths=[
            str((root / "game.exe").resolve()),
            str((root / "game.pck").resolve()),
        ],
        primary_path=str((root / "game.exe").resolve()),
    )
    p5 = report["per_criterion"][0]
    assert p5["satisfied"]
    assert "source_code" not in p5["missing_artifacts"]


def test_godot_pck_satisfies_source_code_in_gate(tmp_path):
    root = tmp_path / "student"
    root.mkdir()
    exe_dir = root / "exe"
    exe_dir.mkdir()
    pck = exe_dir / "game.pck"
    pck.write_bytes(
        b"\0" * 20
        + b"GDPC"
        + b"\0" * 40
        + b"res://main.tscn\x00player.gd\x00enemy.gd\x00"
    )
    (exe_dir / "game.exe").write_bytes(b"MZ" + b"\0" * 64)
    paths = [
        str((exe_dir / "game.exe").resolve()),
        str(pck.resolve()),
    ]
    criteria = [
        {
            "criteria_level": "8/C.P5",
            "criteria_description": "إنتاج لعبة حاسوب",
            "key_points": [],
        },
    ]
    report = evaluate_evidence_completeness(
        grading_criteria=criteria,
        submission_paths=paths,
        primary_path=paths[0],
    )
    p5 = report["per_criterion"][0]
    assert p5["satisfied"]
    assert "source_code" not in p5["missing_artifacts"]
    assert report["assets_detected"]["source_code"]


def test_l4_permitted_with_epoch2_state():
    assert is_l4_sandbox_permitted() is True


if __name__ == "__main__":
    import tempfile

    test_resolve_student_root_from_assets_path(Path(tempfile.mkdtemp()))
    test_expand_submission_paths_includes_exe(Path(tempfile.mkdtemp()))
    test_evidence_gate_flags_missing_gdd(Path(tempfile.mkdtemp()))
    test_l4_permitted_with_epoch2_state()
    print("test_completion_layers: OK")
