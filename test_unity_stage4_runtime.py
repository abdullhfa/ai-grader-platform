import tempfile
import unittest
from pathlib import Path

from app.artifact_inventory import build_runtime_artifacts_summary
from app.runtime_criterion_mapping import evaluate_operational_support
from app.runtime_observation_sandbox import (
    build_runtime_signal_graph,
    detect_unity_build_for_exe,
    parse_unity_player_log,
    summarize_runtime_screenshots,
)
from app.visual_state_classification import (
    classify_visual_state,
    detect_visual_freeze,
)
from app.runtime_process_restriction import (
    build_restriction_report,
    is_suspicious_process,
)


class UnityStage4RuntimeTests(unittest.TestCase):
    def test_parse_unity_player_log_extracts_bounded_signals(self) -> None:
        parsed = parse_unity_player_log(
            "\n".join(
                [
                    "Initialize engine version: 6000.4.2f1 (abc123)",
                    "Input System module state changed to: Initialized.",
                    "UnloadTime: 0.123 ms",
                    "NullReferenceException: Object reference not set",
                    "Crash!!! native crash observed",
                ]
            )
        )

        self.assertEqual(parsed["unity_version_hint"], "6000.4.2f1")
        self.assertGreaterEqual(parsed["error_count"], 1)
        self.assertGreaterEqual(parsed["crash_signal_count"], 1)
        self.assertEqual(len(parsed["scene_load_signals"]), 1)
        self.assertEqual(len(parsed["input_system_signals"]), 1)

    def test_unity_build_detection_uses_player_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "StudentGame.exe"
            data = root / "StudentGame_Data"
            data.mkdir()
            exe.write_bytes(b"MZ")
            (root / "UnityPlayer.dll").write_bytes(b"dll")
            (data / "globalgamemanagers").write_bytes(b"gm")

            detected = detect_unity_build_for_exe(exe)

        self.assertTrue(detected["detected"])
        self.assertEqual(detected["confidence"], "high")
        self.assertTrue(detected["unity_player_dll"])
        self.assertTrue(detected["globalgamemanagers"])

    def test_smoke_signal_graph_does_not_infer_player_movement(self) -> None:
        graph = build_runtime_signal_graph(
            [
                {
                    "type": "exe",
                    "artifact": "Game.exe",
                    "smoke_result": "stable_window",
                    "signals": {
                        "runtime_launch_attempted": True,
                        "runtime_stable": True,
                        "scene_loaded": "partial",
                        "player_moved": "unknown",
                        "crash": "none",
                    },
                }
            ]
        )

        self.assertEqual(graph["signals"]["scene_loaded"], "partial")
        self.assertEqual(graph["signals"]["player_moved"], "unknown")

    def test_smoke_only_runtime_never_suggests_achieved(self) -> None:
        observation = {
            "status": "completed",
            "runtime_observed": True,
            "runtime_verified": False,
            "runtime_signal_graph": {
                "signals": {
                    "scene_loaded": "partial",
                    "player_moved": "unknown",
                    "score_changed": "unknown",
                    "collision_events": "unknown",
                    "level_transition": "unknown",
                    "crash": "none",
                }
            },
            "artifact_analyses": [
                {
                    "type": "exe",
                    "engine": "unity",
                    "artifact": "Game.exe",
                    "smoke_result": "stable_window",
                    "signals": {"crash": "none"},
                }
            ],
        }

        support = evaluate_operational_support(observation, {})

        self.assertTrue(support["C.P5"]["smoke_only"])
        self.assertFalse(support["C.P5"]["suggested_achieved"])
        self.assertTrue(support["C.P5"]["needs_human_playtest"])
        self.assertFalse(support["C.P6"]["suggested_achieved"])

    def test_runtime_summary_links_unity_source_and_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "StudentGame.exe"
            data = root / "StudentGame_Data"
            data.mkdir()
            exe.write_bytes(b"MZ")
            (root / "UnityPlayer.dll").write_bytes(b"dll")
            (data / "globalgamemanagers").write_bytes(b"gm")
            files = [exe, root / "UnityPlayer.dll", data / "globalgamemanagers"]

            summary = build_runtime_artifacts_summary(
                files,
                {
                    "unity_semantic": {
                        "scripts_analyzed": 3,
                        "assets_peeked": 1,
                        "monobehaviour_count": 2,
                    }
                },
            )

        self.assertTrue(summary["unity_build_detected"])
        self.assertEqual(summary["unity_source_build_alignment"], "source_and_build_present")
        self.assertTrue(summary["unity_source_signals"]["source_present"])

    def test_screenshot_summary_is_visual_evidence_only(self) -> None:
        summary = summarize_runtime_screenshots(
            [
                {
                    "label": "launch",
                    "status": "captured",
                    "path": "uploads/debug/runtime_screenshots/Game/launch.png",
                    "visual_stats": {"black_screen_possible": False},
                },
                {
                    "label": "mid_runtime",
                    "status": "unavailable",
                    "errors": ["headless"],
                },
            ]
        )

        self.assertEqual(summary["runtime_screenshot_count"], 1)
        self.assertEqual(summary["visual_runtime_evidence"], "present")
        self.assertFalse(summary["black_screen_possible"])
        self.assertIn("استشاري", summary["authority_note_ar"])

    def test_screenshot_summary_flags_possible_black_screen(self) -> None:
        summary = summarize_runtime_screenshots(
            [
                {
                    "label": "launch",
                    "status": "captured",
                    "path": "launch.png",
                    "visual_stats": {"black_screen_possible": True},
                }
            ]
        )

        self.assertTrue(summary["black_screen_possible"])

    def test_classify_black_screen_heuristic(self) -> None:
        result = classify_visual_state(
            {
                "avg_luma_approx": 8,
                "luma_variance": 10,
                "entropy_approx": 0.5,
                "dynamic_range": 12,
                "center_band_variance": 5,
                "black_screen_possible": True,
            }
        )
        self.assertEqual(result["visual_state"], "black_screen")
        self.assertGreaterEqual(result["visual_state_confidence"], 0.6)

    def test_freeze_detection_flags_identical_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img_path = root / "frame.png"
            try:
                from PIL import Image
            except ImportError:
                self.skipTest("Pillow not available")
            Image.new("RGB", (32, 32), color=(20, 20, 20)).save(img_path)
            summary = detect_visual_freeze(
                [
                    {"status": "captured", "path": str(img_path), "label": "launch"},
                    {"status": "captured", "path": str(img_path), "label": "mid_runtime"},
                ]
            )
        self.assertTrue(summary["freeze_possible"])
        self.assertEqual(summary["compared_pairs"], 1)

    def test_screenshot_summary_includes_visual_states(self) -> None:
        summary = summarize_runtime_screenshots(
            [
                {
                    "label": "launch",
                    "status": "captured",
                    "path": "launch.png",
                    "visual_state": "main_menu_candidate",
                    "visual_state_confidence": 0.52,
                    "visual_stats": {"black_screen_possible": False},
                },
                {
                    "label": "mid_runtime",
                    "status": "captured",
                    "path": "mid.png",
                    "visual_state": "gameplay_candidate",
                    "visual_state_confidence": 0.48,
                    "visual_stats": {"black_screen_possible": False},
                },
            ]
        )
        self.assertIn("main_menu_candidate", summary.get("visual_states_observed", []))
        self.assertGreater(summary.get("visual_runtime_confidence", 0), 0)
        self.assertTrue(summary.get("observed_visual_elements"))
        self.assertTrue(summary.get("human_validation_required"))

    def test_process_restriction_flags_suspicious_names(self) -> None:
        self.assertTrue(is_suspicious_process("powershell.exe"))
        self.assertTrue(is_suspicious_process("CMD.EXE"))
        self.assertFalse(is_suspicious_process("StudentGame.exe"))

    def test_process_restriction_report_shape(self) -> None:
        report = build_restriction_report(
            root_pid=1234,
            scans=[{"process_count": 2, "suspicious_spawns": []}],
            suspicious_events=[{"pid": 999, "name": "powershell.exe"}],
            kill_result={"ok": True, "method": "taskkill_tree"},
        )
        self.assertTrue(report["suspicious_spawn_detected"])
        self.assertEqual(report["max_process_count"], 2)
        self.assertIn("authority_note_ar", report)

    def test_runtime_replay_builds_from_grading_snapshot(self) -> None:
        from app.runtime_replay_viewer import build_runtime_replay, path_to_upload_url

        snapshot = {
            "artifact_inventory": {
                "runtime_observation_report": {
                    "status": "completed",
                    "runtime_session_id": "ros_test123",
                    "runtime_evidence_level": 4,
                    "runtime_observed": True,
                    "runtime_verified": False,
                    "observation_summary_ar": "test summary",
                    "artifact_analyses": [
                        {
                            "artifact": "Game.exe",
                            "type": "exe",
                            "engine": "unity",
                            "smoke_result": "stable_window",
                            "runtime_screenshots": [
                                {
                                    "label": "launch",
                                    "status": "captured",
                                    "path": "uploads/debug/runtime_screenshots/a/launch.png",
                                    "visual_state": "main_menu_candidate",
                                    "visual_state_confidence": 0.5,
                                    "timestamp_sec": 2.0,
                                }
                            ],
                            "unity_observation": {
                                "player_log_found": True,
                                "selected_log_path": "C:/AppData/LocalLow/Co/Game/Player.log",
                                "error_signals": ["NullReferenceException"],
                                "crash_signals": [],
                            },
                            "process_restriction": {
                                "suspicious_spawn_detected": False,
                                "processes_seen": ["Game.exe"],
                            },
                        }
                    ],
                    "visual_observation_summary": [
                        {
                            "observed_visual_elements": ["menu_ui_candidate"],
                            "unverified_gameplay": ["player_movement"],
                            "human_validation_required": ["C.P5 gameplay"],
                            "visual_states_observed": ["main_menu_candidate"],
                            "visual_runtime_confidence": 0.45,
                        }
                    ],
                }
            }
        }
        replay = build_runtime_replay(snapshot, submission_id=42)
        self.assertTrue(replay["available"])
        self.assertEqual(replay["runtime_session_id"], "ros_test123")
        self.assertEqual(len(replay["visual_timeline"]), 1)
        self.assertEqual(replay["executables"][0]["artifact"], "Game.exe")
        self.assertIn("menu_ui_candidate", replay["audit"]["observed_visual_elements"])
        self.assertTrue(replay["human_authority_required"])
        url = path_to_upload_url("uploads/debug/runtime_screenshots/a/launch.png")
        self.assertTrue(url.startswith("/uploads/"))

    def test_runtime_replay_unavailable_without_evidence(self) -> None:
        from app.runtime_replay_viewer import build_runtime_replay

        replay = build_runtime_replay({"artifact_inventory": {}})
        self.assertFalse(replay["available"])

    def test_classify_visual_response_to_input(self) -> None:
        from app.runtime_interaction_trace import classify_visual_response_to_input

        self.assertEqual(
            classify_visual_response_to_input(
                pre_stats={"avg_luma_approx": 10, "luma_variance": 5, "entropy_approx": 1},
                post_stats={"avg_luma_approx": 80, "luma_variance": 40, "entropy_approx": 3},
            ),
            "partial",
        )
        self.assertEqual(
            classify_visual_response_to_input(
                pre_stats={"avg_luma_approx": 50, "luma_variance": 10, "entropy_approx": 2},
                post_stats={"avg_luma_approx": 51, "luma_variance": 10, "entropy_approx": 2},
            ),
            "none",
        )

    def test_interaction_trace_does_not_set_player_moved(self) -> None:
        from app.runtime_interaction_trace import apply_interaction_signals, build_interaction_trace_report

        signals: dict = {"player_moved": "unknown"}
        trace = build_interaction_trace_report(
            {"status": "completed", "interaction_traces_detected": True, "input_count": 7},
            pre_screenshot={"label": "launch", "visual_stats": {"avg_luma_approx": 10, "luma_variance": 5, "entropy_approx": 1}},
            post_screenshot={"label": "post_interaction", "visual_stats": {"avg_luma_approx": 90, "luma_variance": 50, "entropy_approx": 4}},
        )
        apply_interaction_signals(signals, trace)
        self.assertEqual(signals["player_moved"], "unknown")
        self.assertEqual(signals["interaction_input_sent"], "yes")
        self.assertEqual(signals["visual_response_to_input"], "partial")

    def test_automated_interaction_never_suggests_achieved(self) -> None:
        observation = {
            "status": "completed",
            "runtime_observed": True,
            "runtime_verified": False,
            "runtime_signal_graph": {
                "signals": {
                    "scene_loaded": "partial",
                    "player_moved": "unknown",
                    "score_changed": "unknown",
                    "collision_events": "unknown",
                    "level_transition": "unknown",
                    "crash": "none",
                    "interaction_input_sent": "yes",
                    "visual_response_to_input": "partial",
                    "automated_interaction_observed": "yes",
                }
            },
            "artifact_analyses": [
                {
                    "type": "exe",
                    "engine": "unity",
                    "artifact": "Game.exe",
                    "smoke_result": "stable_window",
                    "signals": {
                        "crash": "none",
                        "interaction_input_sent": "yes",
                        "visual_response_to_input": "partial",
                        "automated_interaction_observed": "yes",
                        "player_moved": "unknown",
                    },
                }
            ],
        }
        support = evaluate_operational_support(observation, {})
        self.assertFalse(support["C.P5"]["suggested_achieved"])
        self.assertTrue(support["C.P5"]["needs_human_playtest"])
        self.assertTrue(support.get("automated_interaction_observed"))

    def test_human_playtest_can_suggest_achieved_with_strong_runtime(self) -> None:
        observation = {
            "status": "completed",
            "runtime_observed": True,
            "runtime_verified": True,
            "human_playtest_verified": True,
            "manual_playtest_verified": True,
            "interaction_visually_corroborated": True,
            "runtime_signal_graph": {
                "signals": {
                    "scene_loaded": "partial",
                    "player_moved": "unknown",
                    "crash": "none",
                    "interaction_input_sent": "yes",
                    "visual_response_to_input": "partial",
                    "automated_interaction_observed": "yes",
                }
            },
            "artifact_analyses": [
                {"type": "pck", "valid": True, "artifact": "Game.pck", "signals": {"crash": "none"}},
                {
                    "type": "exe",
                    "engine": "unity",
                    "artifact": "Game.exe",
                    "smoke_result": "stable_window",
                    "signals": {"crash": "none", "interaction_input_sent": "yes"},
                }
            ],
        }
        support = evaluate_operational_support(observation, {})
        self.assertTrue(support["C.P5"]["suggested_achieved"])
        self.assertFalse(support["C.P5"]["needs_human_playtest"])

    def test_submission_playtest_merge_updates_snapshot(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from app.submission_playtest import (
            finalize_submission_playtest,
            merge_playtest_into_grading_snapshot,
            record_submission_playtest_observation,
            start_submission_playtest,
        )

        snapshot = {
            "criteria_results": [
                {"criteria_level": "C.P5", "achieved": False, "score": 0, "max_score": 100},
            ],
            "artifact_inventory": {
                "runtime_observation_report": {
                    "status": "completed",
                    "runtime_session_id": "ros_merge_test",
                    "runtime_observed": True,
                    "runtime_verified": True,
                    "artifact_analyses": [
                        {"type": "pck", "valid": True, "artifact": "Game.pck"},
                        {
                            "type": "exe",
                            "engine": "unity",
                            "artifact": "Game.exe",
                            "smoke_result": "stable_window",
                        }
                    ],
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            session_dir = base / "sessions"
            pass_dir = base / "passes" / "99"
            session_dir.mkdir(parents=True)
            pass_dir.mkdir(parents=True)

            with patch("app.submission_playtest.submission_playtest_dirs") as mock_dirs:
                mock_dirs.return_value = (session_dir, pass_dir)
                with patch("app.manual_playtest_pass.submission_playtest_dirs") as mock_dirs2:
                    mock_dirs2.return_value = (session_dir, pass_dir)
                    record = start_submission_playtest(
                        99,
                        student_name="Test Student",
                        grading_snapshot=snapshot,
                    )
                    for test in record.get("tests") or []:
                        record = record_submission_playtest_observation(
                            99,
                            record["pass_id"],
                            test["test_id"],
                            observed_en="start panel hidden after Space",
                        )
                    result = finalize_submission_playtest(
                        99,
                        record["pass_id"],
                        grading_snapshot=snapshot,
                    )

        updated = result["grading_snapshot"]
        self.assertTrue(updated.get("manual_playtest_pass"))
        obs = updated["artifact_inventory"]["runtime_observation_report"]
        self.assertTrue(obs.get("human_playtest_verified"))
        self.assertTrue(updated.get("runtime_criterion_support", {}).get("C.P5", {}).get("suggested_achieved"))

    def test_human_playtest_uses_l5_authority_in_adjudication(self) -> None:
        from app.runtime_criterion_mapping import apply_runtime_criterion_adjudication

        grading = {
            "criteria_results": [
                {"criteria_level": "C.P5", "achieved": False, "score": 40},
                {"criteria_level": "C.P6", "achieved": False, "score": 40},
            ],
            "artifact_inventory": {
                "runtime_observation_report": {
                    "status": "completed",
                    "runtime_observed": True,
                    "runtime_verified": True,
                    "human_playtest_verified": True,
                    "interaction_visually_corroborated": True,
                    "artifact_analyses": [
                        {"type": "pck", "valid": True, "artifact": "Game.pck"},
                        {
                            "type": "exe",
                            "smoke_result": "stable_window",
                            "signals": {"crash": "none"},
                        }
                    ],
                }
            },
        }
        result = apply_runtime_criterion_adjudication(grading)
        self.assertTrue(result.get("applied"))
        cp5 = next(
            c for c in grading["criteria_results"] if c["criteria_level"] == "C.P5"
        )
        self.assertTrue(cp5.get("achieved"))
        self.assertEqual(cp5.get("achievement_authority"), "HUMAN_PLAYTEST_L5")

    def test_criteria_level_match_helper(self) -> None:
        from app.submission_runtime_adjudication import _criteria_level_match

        self.assertTrue(_criteria_level_match("A.P5", "C.P5"))
        self.assertTrue(_criteria_level_match("C.P5", "C.P5"))
        self.assertFalse(_criteria_level_match("C.P6", "C.P5"))


if __name__ == "__main__":
    unittest.main()
