"""Institutional grade resolution layer tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_referral_when_partial_criteria():
    from app.institutional_grade_resolution import resolve_institutional_classification

    grading = {
        "grade_level": "U",
        "percentage": 55,
        "criteria_results": [
            {"achieved": True, "criteria_level": "8.C.P4"},
            {"achieved": False, "criteria_level": "8.C.P5"},
        ],
        "artifact_inventory": {
            "executable_artifacts": {"files": [{"name": "game.exe"}]},
            "runtime_observation_report": {
                "status": "completed",
                "engine": "godot",
                "runtime_observed": True,
            },
        },
    }
    res = resolve_institutional_classification(grading)
    assert res["outcome_band"] in ("Referral", "Partial")
    assert res["btec_grade"] == "U"
    assert "فشل" not in (res.get("runtime_resolution") or {}).get("summary_ar", "")


def test_partial_runtime_on_failed_status():
    from app.institutional_grade_resolution import build_runtime_resolution_summary

    res = build_runtime_resolution_summary(
        observation={
            "status": "failed",
            "engine": "legacy_exe",
            "platform_analyses": [
                {
                    "signals": {
                        "legacy_observation": {
                            "runtime_observed": True,
                            "smoke_result": "launch_ok",
                        }
                    }
                }
            ],
        },
        inventory={"executable_artifacts": {"files": [{"name": "game.exe"}]}},
    )
    assert "partial_gameplay_or_smoke_incomplete" in res["outcomes"]
    assert res["summary_ar"].startswith("تشغيل جزئي")


def test_tier_b_when_smoke_failed_status():
    from app.submission.confidence_tiers import compute_confidence_tier

    tier = compute_confidence_tier(
        engine_id="legacy_exe",
        status="failed",
        runtime_method="legacy_smoke_test",
    )
    assert tier["tier"] == "B"


def test_gameplay_semantic_flags_progression_missing():
    from app.gameplay_semantic_verification import assess_gameplay_semantics

    sem = assess_gameplay_semantics(
        {
            "runtime_observed": True,
            "runtime_screenshots": [
                {"status": "captured", "visual_state": "gameplay_candidate"},
                {"status": "captured", "visual_state": "gameplay_candidate"},
            ],
            "runtime_signal_graph": {
                "signals": {
                    "player_moved": "detected",
                    "score_changed": "no",
                    "level_transition": "no",
                    "collision_events": "detected",
                }
            },
        }
    )
    assert sem["interaction_detected"] is True
    assert sem["progression_missing"] is True
    assert sem["loop_incomplete"] is True
    assert sem["verification_level"] in ("L4_plus", "L4")


def test_runtime_resolution_reflects_loop_incomplete():
    from app.institutional_grade_resolution import build_runtime_resolution_summary

    res = build_runtime_resolution_summary(
        observation={
            "status": "completed",
            "engine": "godot",
            "runtime_observed": True,
            "runtime_screenshots": [
                {"status": "captured", "visual_state": "gameplay_candidate"},
                {"status": "captured", "visual_state": "gameplay_candidate"},
            ],
            "runtime_signal_graph": {
                "signals": {
                    "player_moved": "detected",
                    "collision_events": "detected",
                    "level_transition": "no",
                    "score_changed": "no",
                }
            },
        },
        inventory={"executable_artifacts": {"files": [{"name": "final.exe"}]}},
    )
    assert "gameplay_loop_incomplete" in res["outcomes"]
    assert "progression_missing" in res["outcomes"]
    assert "مكتملة" in res["summary_ar"] or "غير مُثبت" in res["summary_ar"]


def test_gameplay_semantic_detects_restart_menu_and_score_progression():
    from app.gameplay_semantic_verification import assess_gameplay_semantics

    sem = assess_gameplay_semantics(
        {
            "runtime_observed": True,
            "runtime_screenshots": [
                {
                    "status": "captured",
                    "visual_state": "gameplay_candidate",
                    "observed_visual_elements": ["menu", "restart", "lives"],
                },
                {"status": "captured", "visual_state": "gameplay_candidate"},
            ],
            "runtime_signal_graph": {
                "signals": {
                    "player_moved": "detected",
                    "score_changed": "detected",
                    "level_transition": "detected",
                    "fail_state": "detected",
                    "menu_navigation": "detected",
                    "restart_flow": "detected",
                    "health_changed": "detected",
                }
            },
        }
    )
    assert sem["score_progression_detected"] is True
    assert sem["restart_flow_detected"] is True
    assert sem["menu_navigation_detected"] is True
    assert sem["health_or_lives_detected"] is True
    assert sem["verification_level"] == "L5_verified"
    assert sem["gameplay_loop_complete"] is True


def test_godot_prefers_final_pck():
    from app.runtime_engines.godot.export_runner import find_godot_runnable_artifacts

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        exe_dir = root / "exe"
        exe_dir.mkdir()
        (exe_dir / "farst game.exe").write_bytes(b"MZ" + b"\0" * 64)
        (exe_dir / "farst game.pck").write_bytes(b"GDPC" + b"\0" * 80)
        (exe_dir / "final.pck").write_bytes(b"GDPC" + b"\0" * 2000)

        layout = find_godot_runnable_artifacts(root)
        assert layout.get("pck") and layout["pck"].name.lower() == "final.pck"
