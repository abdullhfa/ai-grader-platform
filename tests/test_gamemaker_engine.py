"""Tests for GameMaker runtime engine and normalization."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestGameMakerEngine(unittest.TestCase):
    def test_yyp_detection(self):
        from app.runtime_engines.gamemaker.engine import GameMakerRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            yyp = root / "Demo.yyp"
            yyp.write_text(
                json.dumps({"resourceType": "GMProject", "resources": [{"id": "1"}], "name": "Demo"}),
                encoding="utf-8",
            )
            (root / "objects" / "obj_player").mkdir(parents=True)
            (root / "objects" / "obj_player" / "Create_0.gml").write_text(
                "keyboard_check(vk_left);\ncollision_circle(x,y,8,obj_enemy,false,true);",
                encoding="utf-8",
            )
            score = GameMakerRuntimeEngine.detect(root)
            self.assertGreaterEqual(score, 0.9)

    def test_yyz_extract(self):
        from app.runtime_engines.gamemaker.yyz_parser import extract_yyz_archive

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            yyz = root / "pack.yyz"
            yyp_content = json.dumps({"resourceType": "GMProject", "resources": []})
            with zipfile.ZipFile(yyz, "w") as zf:
                zf.writestr("Demo/Demo.yyp", yyp_content)
            out = root / "extract"
            result = extract_yyz_archive(yyz, out)
            self.assertTrue(result.get("success"))
            self.assertTrue((out / "Demo" / "Demo.yyp").is_file())

    def test_artifact_analysis_session(self):
        from app.runtime.orchestrator import run_runtime_session

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.yyp").write_text(
                json.dumps({"resourceType": "GMProject", "resources": [{"a": 1}, {"b": 2}]}),
                encoding="utf-8",
            )
            gml_dir = root / "objects" / "obj_ctrl"
            gml_dir.mkdir(parents=True)
            (gml_dir / "Step_0.gml").write_text("score += 1;\nroom_goto_next();", encoding="utf-8")
            result = run_runtime_session("demo_gm", root, timeout_seconds=5)
            self.assertEqual(result.get("engine"), "gamemaker")
            self.assertIn(result.get("status"), ("completed", "failed", "skipped"))
            norm = result.get("normalized") or {}
            self.assertEqual(norm.get("runtime_observation", {}).get("engine_id"), "gamemaker")

    def test_gamemaker_exe_beats_legacy_when_yyp_present(self):
        from app.runtime_engines.registry import resolve_engine
        from app.runtime_engines.gamemaker.engine import GameMakerRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")
            (root / "Game.exe").write_bytes(b"MZ")
            resolved = resolve_engine(root)
            self.assertIs(resolved, GameMakerRuntimeEngine)


class TestRuntimeNormalization(unittest.TestCase):
    def test_normalize_manifest(self):
        from app.runtime_engines.normalization import normalize_runtime_manifest

        manifest = {
            "session_id": "s1",
            "engine": "godot",
            "submission_key": "k1",
            "status": "completed",
            "signals": {"runtime_method": "godot_export_smoke"},
            "metrics": {"crash_detected": False},
            "events": [{"event": "export_done", "timestamp": 1.0}],
            "screenshots": [],
            "logs": [],
            "artifacts": [],
        }
        norm = normalize_runtime_manifest(manifest)
        self.assertIn("runtime_observation", norm)
        self.assertIn("evidence_bundle", norm)
        self.assertEqual(norm["runtime_observation"]["engine_id"], "godot")


if __name__ == "__main__":
    unittest.main()
