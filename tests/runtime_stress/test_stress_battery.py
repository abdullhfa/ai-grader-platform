"""
PHASE C — Runtime stress battery tests.
Run: python tests/runtime_stress/test_stress_battery.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestRuntimeStressBattery(unittest.TestCase):
    def _abdullah_snapshot(self):
        from app.database import SessionLocal
        from app.models import Submission

        db = SessionLocal()
        try:
            sub = db.query(Submission).filter(Submission.id == 1).first()
            if not sub or not sub.grading_snapshot_json:
                self.skipTest("submission 1 not available")
            return json.loads(str(sub.grading_snapshot_json))
        finally:
            db.close()

    def test_crash_on_launch_detected(self):
        from app.runtime.stress_harness import run_stress_scenario

        r = run_stress_scenario("crash_on_launch", write_log=False)
        self.assertTrue(r.get("detect_crash"))

    def test_infinite_loop_times_out(self):
        from app.runtime.stress_harness import run_stress_scenario

        r = run_stress_scenario("infinite_loop", timeout_seconds=2, write_log=False)
        self.assertIn(r.get("observation_status"), ("timeout", "error"))

    def test_hung_process_killed(self):
        from app.runtime.stress_harness import run_stress_scenario

        r = run_stress_scenario("hung_process", timeout_seconds=2, write_log=False)
        self.assertEqual(r.get("observation_status"), "timeout")

    def test_missing_dll_mock(self):
        from app.runtime.stress_harness import run_stress_scenario

        r = run_stress_scenario("missing_dll", write_log=False)
        self.assertTrue(r.get("detect_crash"))

    def test_freeze_mock(self):
        from app.runtime.stress_harness import run_stress_scenario

        r = run_stress_scenario("fullscreen_freeze", write_log=False)
        self.assertTrue(r.get("detect_freeze"))

    def test_replay_integrity_preserved(self):
        from app.runtime.stress_harness import run_stress_scenario

        snap = self._abdullah_snapshot()
        r = run_stress_scenario("dead_input_state", snapshot=snap, write_log=False)
        rep = r.get("replay_integrity") or {}
        self.assertTrue(rep.get("protected_digest_match"))

    def test_full_battery(self):
        from app.runtime.stress_harness import run_full_stress_battery

        report = run_full_stress_battery()
        self.assertGreaterEqual(report.get("scenario_count", 0), 10)
        self.assertGreaterEqual(report.get("scenarios_passed", 0), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
