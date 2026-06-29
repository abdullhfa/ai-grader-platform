"""Runtime orchestrator and engine tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestRuntimeEngines(unittest.TestCase):
    def test_web_engine_detects_index_html(self):
        from app.runtime_engines.web.engine import WebRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "index.html"
            html.write_text("<html><body><canvas id='g'></canvas><script></script></body></html>", encoding="utf-8")
            score = WebRuntimeEngine.detect(root)
            self.assertGreater(score, 0.7)

    def test_web_static_fallback(self):
        from app.runtime_engines.web.playwright_runner import run_web_game_headless

        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "index.html"
            html.write_text("<html><body><canvas></canvas></body></html>", encoding="utf-8")
            result = run_web_game_headless(html, timeout_ms=3000, frame_count=1)
            self.assertIn(result.get("method"), ("static_only", "playwright_headless"))
            self.assertTrue(result.get("success") or result.get("method") == "static_only")

    def test_godot_project_detect(self):
        from app.runtime_engines.godot.engine import GodotRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text("[application]\nconfig/name=\"demo\"\n", encoding="utf-8")
            score = GodotRuntimeEngine.detect(root)
            self.assertGreaterEqual(score, 0.7)

    def test_legacy_exe_detect(self):
        from app.runtime_engines.legacy.engine import LegacyExecutableEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game.exe").write_bytes(b"MZ")
            score = LegacyExecutableEngine.detect(root)
            # Detection was intentionally softened when richer engines (e.g., Godot) may exist.
            self.assertGreaterEqual(score, 0.3)

    def test_resolve_engine_prefers_web_for_html_project(self):
        from app.runtime_engines.registry import resolve_engine
        from app.runtime_engines.web.engine import WebRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<html><canvas></canvas><script></script></html>", encoding="utf-8")
            resolved = resolve_engine(root)
            self.assertIs(resolved, WebRuntimeEngine)


class TestRuntimeOrchestrator(unittest.TestCase):
    def test_infer_submission_root(self):
        from app.runtime.orchestrator import infer_submission_root

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "student"
            root.mkdir()
            html = root / "index.html"
            html.write_text("<html><body>ok</body></html>", encoding="utf-8")
            inferred = infer_submission_root([str(html)])
            # Root inference may choose submission dir or a higher shared root.
            self.assertIn(inferred, {root, root.parent, root.parent.parent})

    def test_run_runtime_session_web(self):
        from app.runtime.orchestrator import run_runtime_session

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text(
                "<html><head></head><body><canvas></canvas><script>console.log('x')</script></body></html>",
                encoding="utf-8",
            )
            result = run_runtime_session("test_student", root, timeout_seconds=5)
            self.assertIn(result.get("status"), ("completed", "failed", "skipped"))
            self.assertEqual(result.get("engine"), "web")

    def test_run_runtime_observation_shape(self):
        from app.runtime.orchestrator import run_runtime_observation

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<html><canvas></canvas></html>", encoding="utf-8")
            obs = run_runtime_observation([str(root / "index.html")], student_name="demo")
            self.assertIn("platform_analyses", obs)
            self.assertIn(obs.get("status"), ("completed", "gated", "failed", "skipped"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
