"""Godot runtime engine tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestGodotExportRunner(unittest.TestCase):
    def test_parse_export_presets(self):
        from app.runtime_engines.godot.export_runner import _parse_export_presets

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "export_presets.cfg").write_text(
                '[preset.0]\nname="Windows Desktop"\nplatform="Windows Desktop"\n'
                'export_path="build/game.exe"\n',
                encoding="utf-8",
            )
            presets = _parse_export_presets(root)
            self.assertEqual(len(presets), 1)
            self.assertEqual(presets[0]["name"], "Windows Desktop")

    def test_static_analysis(self):
        from app.runtime_engines.godot.export_runner import analyze_godot_project

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text(
                '[application]\nconfig/name="Demo"\nrun/main_scene="res://main.tscn"\n',
                encoding="utf-8",
            )
            (root / "main.gd").write_text("extends Node2D\n", encoding="utf-8")
            (root / "main.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
            analysis = analyze_godot_project(root)
            self.assertEqual(analysis["mode"], "godot_static_analysis")
            self.assertGreaterEqual(analysis["script_count"], 1)
            self.assertGreaterEqual(analysis["completeness_hint"], 0.5)


class TestGodotEditorDetection(unittest.TestCase):
    def test_rejects_godot_editor_exe(self):
        from app.runtime_engines.godot.export_runner import (
            find_godot_runnable_artifacts,
            is_godot_editor_executable,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text('[application]\nconfig/name="x"\n', encoding="utf-8")
            tools = root / "أدوات التصدير"
            tools.mkdir()
            editor = tools / "Godot_v4.6-stable_win64.exe"
            editor.write_bytes(b"MZ" + b"\0" * 200)
            run_dir = root / "ملفات تشغيل اللعبة"
            run_dir.mkdir()
            pck = run_dir / "P_03.pck"
            pck.write_bytes(b"GDPC" + b"\0" * 100)
            game = run_dir / "P_03.exe"
            game.write_bytes(b"MZ" + b"\0" * 200)

            self.assertTrue(is_godot_editor_executable(editor))
            layout = find_godot_runnable_artifacts(root)
            self.assertEqual(layout.get("executable"), game)
            self.assertEqual(layout.get("pck"), pck)


class TestGodotRuntimeEngine(unittest.TestCase):
    def test_detect_project(self):
        from app.runtime_engines.godot.engine import GodotRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text('[application]\nconfig/name="x"\n', encoding="utf-8")
            self.assertGreaterEqual(GodotRuntimeEngine.detect(root), 0.9)

    def test_static_fallback_session(self):
        from app.runtime.orchestrator import run_runtime_session

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text(
                '[application]\nconfig/name="Demo"\nrun/main_scene="res://main.tscn"\n',
                encoding="utf-8",
            )
            (root / "player.gd").write_text("extends CharacterBody2D\n", encoding="utf-8")
            result = run_runtime_session("godot_demo", root, timeout_seconds=5)
            self.assertEqual(result.get("engine"), "godot")
            self.assertIn(result.get("status"), ("completed", "failed", "skipped", "gated"))
            if result.get("status") == "completed":
                self.assertIn(
                    result.get("signals", {}).get("runtime_method"),
                    (
                        "godot_static_analysis",
                        "godot_exe_smoke",
                        "godot_pck_smoke",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
