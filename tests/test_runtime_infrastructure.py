"""Infrastructure tests for runtime capabilities, events, artifacts — Phase 2."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestRuntimeInfrastructure(unittest.TestCase):
    def test_session_artifact_store_layout(self):
        from app.runtime_engines.session_artifact_store import SessionArtifactStore

        with tempfile.TemporaryDirectory() as td:
            store = SessionArtifactStore(session_root=Path(td) / "sess")
            store.ensure()
            self.assertTrue(store.screenshots.is_dir())
            self.assertTrue(store.gameplay_video.is_dir())
            self.assertTrue(store.runtime_events.is_dir())

    def test_runtime_event_log(self):
        from app.runtime_engines.events import RuntimeEventLog

        log = RuntimeEventLog()
        log.record("scene_loaded", scene="Main")
        self.assertEqual(len(log.events), 1)
        self.assertEqual(log.events[0].type, "scene_loaded")

    def test_unity_capabilities(self):
        from app.runtime_engines.unity.engine import UnityRuntimeEngine

        caps = UnityRuntimeEngine.capabilities()
        self.assertTrue(caps.supports_build_from_source)
        self.assertTrue(caps.supports_telemetry)
        self.assertTrue(caps.supports_video_capture)

    def test_runtime_session_creates_manifest(self):
        from app.runtime_engines.base import RuntimeSession, SessionStatus
        from app.runtime_engines.unity.engine import UnityRuntimeEngine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            session = RuntimeSession.create(engine="unity", submission_key="student", root=root)
            session.status = SessionStatus.COMPLETED
            session.events.record("test_event")
            manifest = UnityRuntimeEngine().collect_evidence(session)
            self.assertTrue(session.artifact_store.manifest_path.is_file())
            self.assertEqual(manifest["engine"], "unity")
            self.assertIn("events", manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
