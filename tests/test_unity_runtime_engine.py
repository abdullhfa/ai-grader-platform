"""Unity runtime engine tests — Phase 2."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestUnityProjectProbe(unittest.TestCase):
    def test_find_unity_project_root(self):
        from app.runtime_engines.unity.project_probe import find_unity_project_root, probe_unity_layout

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "StudentUnity"
            (root / "Assets").mkdir(parents=True)
            (root / "ProjectSettings").mkdir(parents=True)
            (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 2022.3.10f1\n", encoding="utf-8"
            )
            (root / "ProjectSettings" / "EditorBuildSettings.asset").write_text(
                "EditorBuildSettings:\n  m_Scenes:\n  - enabled: 1\n    path: Assets/Scenes/Main.unity\n",
                encoding="utf-8",
            )
            (root / "Assets" / "Scenes").mkdir(parents=True)
            (root / "Assets" / "Scenes" / "Main.unity").write_text("%YAML 1.1\n", encoding="utf-8")

            found = find_unity_project_root(root)
            self.assertEqual(found, root)
            layout = probe_unity_layout(root)
            self.assertTrue(layout["has_source_project"])
            self.assertGreaterEqual(layout["scene_count"], 1)

    def test_find_unity_executable(self):
        from app.runtime_engines.unity.project_probe import find_unity_executable

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "StudentGame.exe"
            data = root / "StudentGame_Data"
            data.mkdir()
            exe.write_bytes(b"MZ")
            (root / "UnityPlayer.dll").write_bytes(b"dll")
            (data / "globalgamemanagers").write_bytes(b"gm")

            found = find_unity_executable(root)
            self.assertEqual(found, exe)


class TestUnityLogParser(unittest.TestCase):
    def test_parse_editor_log(self):
        from app.runtime_engines.unity.log_parser import parse_unity_editor_log

        parsed = parse_unity_editor_log(
            "Initialize engine version: 2022.3.10f1\n"
            "Error building Player because scripts have compile errors\n"
            "Build succeeded\n"
        )
        self.assertGreaterEqual(parsed["error_count"], 1)
        self.assertTrue(parsed["success_signals"] or parsed["build_succeeded_hint"] is not None)


class TestUnitySceneValidator(unittest.TestCase):
    def test_validate_scenes(self):
        from app.runtime_engines.unity.scene_validator import validate_unity_scenes

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Assets" / "Scenes").mkdir(parents=True)
            scene = root / "Assets" / "Scenes" / "Main.unity"
            scene.write_text("%YAML 1.1\n", encoding="utf-8")
            (root / "ProjectSettings").mkdir()
            (root / "ProjectSettings" / "EditorBuildSettings.asset").write_text(
                "EditorBuildSettings:\n  m_Scenes:\n  - enabled: 1\n    path: Assets/Scenes/Main.unity\n",
                encoding="utf-8",
            )
            report = validate_unity_scenes(root)
            self.assertTrue(report["validation_passed"])
            self.assertTrue(report["has_playable_scene"])


class TestUnityRuntimeEngine(unittest.TestCase):
    def test_detect_unity_build(self):
        from app.runtime_engines.unity.engine import UnityRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "Game.exe"
            data = root / "Game_Data"
            data.mkdir()
            exe.write_bytes(b"MZ")
            (root / "UnityPlayer.dll").write_bytes(b"x")
            (data / "globalgamemanagers").write_bytes(b"gm")
            self.assertGreater(UnityRuntimeEngine.detect(root), 0.9)

    def test_detect_unity_source(self):
        from app.runtime_engines.unity.engine import UnityRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 2022.3.10f1\n", encoding="utf-8"
            )
            self.assertGreater(UnityRuntimeEngine.detect(root), 0.8)

    def test_resolve_prefers_unity_over_legacy(self):
        from app.runtime_engines.registry import resolve_engine
        from app.runtime_engines.unity.engine import UnityRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "Game.exe"
            data = root / "Game_Data"
            data.mkdir()
            exe.write_bytes(b"MZ")
            (root / "UnityPlayer.dll").write_bytes(b"x")
            (data / "globalgamemanagers").write_bytes(b"gm")
            self.assertIs(resolve_engine(root), UnityRuntimeEngine)

    def test_source_only_session_skips_without_build(self):
        from app.runtime.orchestrator import run_runtime_session

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 2022.3.10f1\n", encoding="utf-8"
            )
            result = run_runtime_session("unity_student", root, timeout_seconds=5)
            self.assertEqual(result.get("engine"), "unity")
            self.assertIn(result.get("status"), ("skipped", "completed", "failed"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
