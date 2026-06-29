"""Gameplay AI pipeline tests — Phase 3."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestGameplayPipeline(unittest.TestCase):
    def _make_synthetic_frames(self, root: Path, count: int = 4) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")
        shot_dir = root / "screenshots"
        shot_dir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            img = Image.new("RGB", (320, 240), color=(20 + i * 30, 40, 60))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"Score: {100 + i * 5}", fill=(255, 255, 255))
            img.save(shot_dir / f"frame_{i:02d}.png")

    def test_freeze_detector_on_static_frames(self):
        from app.gameplay_ai.cv.freeze_detector import detect_freeze

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_synthetic_frames(root, 4)
            paths = sorted((root / "screenshots").glob("*.png"))
            # Make frames identical → freeze
            base = paths[0].read_bytes()
            for p in paths[1:]:
                p.write_bytes(base)
            result = detect_freeze(paths)
            self.assertEqual(result.label, "freeze_detected")
            self.assertGreater(result.confidence, 0.7)

    def test_motion_detector_on_changing_frames(self):
        from app.gameplay_ai.cv.motion_detector import detect_motion

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_synthetic_frames(root, 4)
            paths = sorted((root / "screenshots").glob("*.png"))
            result = detect_motion(paths)
            self.assertEqual(result.label, "movement_detected")

    def test_scene_change_detector(self):
        from app.gameplay_ai.cv.scene_change import detect_scene_changes

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_synthetic_frames(root, 4)
            paths = sorted((root / "screenshots").glob("*.png"))
            timestamps = [float(i) for i in range(len(paths))]
            result, events = detect_scene_changes(paths, timestamps)
            self.assertGreaterEqual(result.confidence, 0.5)

    def test_gameplay_pipeline_end_to_end(self):
        from app.gameplay_ai.pipeline import run_gameplay_pipeline
        from app.gameplay_ai.session_model import GameplayRecordingSession

        with tempfile.TemporaryDirectory() as td:
            artifact_root = Path(td)
            self._make_synthetic_frames(artifact_root, 3)
            paths = sorted((artifact_root / "screenshots").glob("*.png"))
            session = GameplayRecordingSession(
                session_id="sess-001",
                submission_key="test_student",
                artifact_root=artifact_root,
                frame_paths=paths,
                frame_timestamps=[0.0, 1.0, 2.0],
                telemetry={"fps_samples": [30, 29, 28], "avg_fps": 29.0},
            )
            result = run_gameplay_pipeline(session)
            self.assertGreater(len(result.detections), 5)
            self.assertGreater(len(result.timeline.events), 0)
            self.assertTrue((artifact_root / "gameplay_analysis" / "analysis.json").is_file())

    def test_evidence_correlation(self):
        from app.gameplay_ai.evidence_linker import correlate_evidence
        from app.gameplay_ai.session_model import DetectionResult

        links = correlate_evidence(
            [
                DetectionResult("motion_detector", "movement_detected", 0.85, {}),
                DetectionResult("win_detector", "win_not_detected", 0.55, {}),
            ]
        )
        self.assertTrue(any(link["criterion_hint"] == "gameplay_loop" for link in links))

    def test_timeline_model(self):
        from app.gameplay_ai.event_bus import GameplayEventBus

        bus = GameplayEventBus()
        bus.emit("scene_loaded", timestamp=1.0, confidence=0.9)
        bus.emit("movement_detected", timestamp=5.0, confidence=0.8)
        summary = bus.timeline.to_dict()
        self.assertEqual(summary["event_count"], 2)
        self.assertIn("01s scene_loaded", summary["summary_lines"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
