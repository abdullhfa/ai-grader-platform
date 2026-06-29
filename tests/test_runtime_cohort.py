"""Tests for STEP 3 runtime cohort runner."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestRuntimeCohort(unittest.TestCase):
    def test_fixture_paths_stay_local(self):
        from app.calibration.runtime_cohort.runner import _collect_paths_from_fixture

        root = ROOT / "cohort_fixtures/python_console_ok"
        paths = _collect_paths_from_fixture(root, "main.py")
        self.assertGreaterEqual(len(paths), 1)
        self.assertTrue(all("cohort_fixtures" in p for p in paths))

    def test_replay_trials_deterministic_hash(self):
        from app.calibration.runtime_cohort.runner import run_replay_stability_trials

        snap = {
            "success": True,
            "grade_level": "P",
            "total_score": 100,
            "max_score": 200,
            "criteria_results": [{"criteria_level": "8/B.P1", "achieved": True, "score": 50}],
            "explainability_revision": {"policy_version": "2.1"},
        }
        result = run_replay_stability_trials(snap, trials=3)
        self.assertTrue(result["hash_stable"])
        self.assertEqual(result["unique_state_hashes"], 1)

    def test_run_fixtures_cohort(self):
        from app.calibration.runtime_cohort.runner import run_cohort

        cfg = ROOT / "app/calibration/runtime_cohort/cohort_config_v1.json"
        report = run_cohort(cfg, ROOT, fixtures_only=True, run_runtime=True)
        self.assertEqual(report["report_type"], "runtime_cohort_v1")
        self.assertEqual(report["entry_count"], 5)
        launched = report["summary"]["runtime_actually_launched"]
        self.assertEqual(len(launched), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
